"""Configura la base de datos para el pipeline de calidad + ML.

Idempotente. Hace:

1. Columnas de analÃ­tica en `calidad_piezas.revisiones_piezas`
   (herramienta, desgaste, temperatura) â€” aditivas y nullable.
2. Ãndices para el pivote de mediciones.
3. Roles `pipeline_rw` (escritura) y `powerbi_ro` (solo lectura).
4. Vistas en `public` para el equipo de ML.
5. Escribe `docs/supabase_setup.sql` (sin contraseÃ±as) y `.env` (con ellas).

Uso:  python tools/configurar_bd.py
"""

from __future__ import annotations

import json
import re
import secrets
import ssl
from pathlib import Path

import pg8000.dbapi

ESQUEMA = "calidad_piezas"
SALON = Path(__file__).resolve().parent.parent
PROYECTO = SALON.parent / "linea_produccion"


# ---------------------------------------------------------------------------
# ConexiÃ³n
# ---------------------------------------------------------------------------
def _leer_env(ruta: Path) -> dict[str, str]:
    datos: dict[str, str] = {}
    if not ruta.exists():
        return datos
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        datos[clave.strip()] = valor.strip()
    return datos


def conectar():
    cfg = json.loads((PROYECTO / "config" / "base_datos.json").read_text(encoding="utf-8"))
    password = _leer_env(PROYECTO / "config" / ".env").get("ENSAMBLE_DB_PASSWORD")
    if not password:
        raise SystemExit("Falta ENSAMBLE_DB_PASSWORD en linea_produccion/config/.env")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return pg8000.dbapi.connect(
        host=cfg["host"],
        port=int(cfg["puerto"]),
        database=cfg["base"],
        user=cfg["usuario"],
        password=password,
        timeout=30,
        ssl_context=ctx,
    )


def password_guardada(variable: str, actual: dict[str, str]) -> str:
    """Reutiliza la clave del .env para no cambiarla en cada ejecuciÃ³n."""
    return actual.get(variable) or secrets.token_urlsafe(18)


# ---------------------------------------------------------------------------
# CatÃ¡logo
# ---------------------------------------------------------------------------
def leer_cotas(con) -> list[str]:
    cur = con.cursor()
    cur.execute(
        f"SELECT codigo_cota FROM {ESQUEMA}.cotas_definicion ORDER BY id_pieza, codigo_cota"
    )
    codigos = [str(fila[0]) for fila in cur.fetchall()]
    cur.close()
    return codigos


def nombre_columna(codigo: str) -> str:
    return "cota_" + codigo.lower().replace("-", "_")


# ---------------------------------------------------------------------------
# Vistas
# ---------------------------------------------------------------------------
def sql_vista_entrenamiento(codigos: list[str]) -> str:
    pivote = ",\n".join(
        "        MAX(CASE WHEN c.codigo_cota = '%s' THEN m.valor_medido END) AS %s"
        % (codigo, nombre_columna(codigo))
        for codigo in codigos
    )
    return f"""
-- ---------------------------------------------------------------------
-- Vista 1: una fila por pieza, con las {len(codigos)} cotas medidas.
-- Sirve para clasificaciÃ³n y control de calidad automatizado.
-- La ÃšLTIMA columna (`conforme`) es el objetivo binario 1/0.
-- No incluye ids ni series: son texto de alta cardinalidad y no aportan.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_entrenamiento_piezas AS
SELECT
    p.codigo_pieza,
    r.temperatura_c,
    r.piezas_en_herramienta,
{pivote},
    CASE WHEN r.resultado_general = 'APROBADO' THEN 0 ELSE 1 END AS defectuosa
FROM {ESQUEMA}.revisiones_piezas r
JOIN {ESQUEMA}.piezas p ON p.id_pieza = r.id_pieza
LEFT JOIN {ESQUEMA}.mediciones_detalle m ON m.id_revision = r.id_revision
LEFT JOIN {ESQUEMA}.cotas_definicion c ON c.id_cota = m.id_cota
GROUP BY r.id_revision, p.codigo_pieza, r.temperatura_c,
         r.piezas_en_herramienta, r.resultado_general;
"""


SQL_VISTA_RIESGO = f"""
-- ---------------------------------------------------------------------
-- Vista 2: solo covariables, SIN medidas de la pieza.
-- Es la vista para predecir ANTES de medir (riesgo, deriva, mantenimiento).
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_riesgo_piezas AS
SELECT
    p.codigo_pieza,
    r.temperatura_c,
    r.piezas_en_herramienta,
    EXTRACT(HOUR FROM r.fecha_revision)::int AS hora_dia,
    CASE WHEN r.resultado_general = 'APROBADO' THEN 0 ELSE 1 END AS defectuosa
FROM {ESQUEMA}.revisiones_piezas r
JOIN {ESQUEMA}.piezas p ON p.id_pieza = r.id_pieza;
"""


# ---------------------------------------------------------------------------
# Archivo setup para el repositorio (sin contraseÃ±as reales)
# ---------------------------------------------------------------------------
def sql_setup_completo(codigos: list[str]) -> str:
    pivote = ",\n".join(
        "        MAX(CASE WHEN c.codigo_cota = '%s' THEN m.valor_medido END) AS %s"
        % (codigo, nombre_columna(codigo))
        for codigo in codigos
    )
    columnas = ",\n".join("    " + nombre_columna(c) for c in codigos)
    _ = columnas

    return f"""-- =====================================================================
-- Setup de base de datos â€” Control de Calidad Dimensional + ML
-- Generado por tools/configurar_bd.py
--
-- Ejecutar completo en Supabase -> SQL Editor.
-- ANTES de ejecutarlo, cambia las dos contraseÃ±as marcadas como CAMBIAR.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS {ESQUEMA};
SET search_path TO {ESQUEMA}, public;

-- ------------------------------ Tablas ------------------------------
CREATE TABLE IF NOT EXISTS {ESQUEMA}.piezas (
    id_pieza SERIAL PRIMARY KEY,
    codigo_pieza VARCHAR(50) UNIQUE NOT NULL,
    nombre_pieza VARCHAR(100) NOT NULL,
    descripcion TEXT,
    unidad_medida VARCHAR(10) DEFAULT 'mm',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS {ESQUEMA}.cotas_definicion (
    id_cota SERIAL PRIMARY KEY,
    id_pieza INT NOT NULL REFERENCES {ESQUEMA}.piezas(id_pieza) ON DELETE CASCADE,
    codigo_cota VARCHAR(20) NOT NULL,
    nombre_caracteristica VARCHAR(150) NOT NULL,
    tipo_cota VARCHAR(30) CHECK (
        tipo_cota IN ('Lineal', 'DiÃ¡metro', 'Radio', 'Ãngulo', 'Espesor')
    ),
    valor_nominal NUMERIC(10, 2) NOT NULL,
    tolerancia_inferior NUMERIC(6, 3) DEFAULT -0.500,
    tolerancia_superior NUMERIC(6, 3) DEFAULT 0.500,
    CONSTRAINT uq_cota_pieza UNIQUE (id_pieza, codigo_cota)
);

CREATE TABLE IF NOT EXISTS {ESQUEMA}.revisiones_piezas (
    id_revision SERIAL PRIMARY KEY,
    id_pieza INT NOT NULL REFERENCES {ESQUEMA}.piezas(id_pieza),
    numero_serie_pieza VARCHAR(100) NOT NULL,
    inspector VARCHAR(100) NOT NULL,
    fecha_revision TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resultado_general VARCHAR(20) CHECK (
        resultado_general IN ('APROBADO', 'RECHAZADO', 'REPARACION')
    ),
    observaciones TEXT,
    id_herramienta VARCHAR(30),
    piezas_en_herramienta INTEGER,
    temperatura_c NUMERIC(6, 2)
);

CREATE TABLE IF NOT EXISTS {ESQUEMA}.mediciones_detalle (
    id_medicion SERIAL PRIMARY KEY,
    id_revision INT NOT NULL REFERENCES {ESQUEMA}.revisiones_piezas(id_revision)
        ON DELETE CASCADE,
    id_cota INT NOT NULL REFERENCES {ESQUEMA}.cotas_definicion(id_cota),
    valor_medido NUMERIC(10, 2) NOT NULL,
    es_conforme BOOLEAN,
    instrumento_medicion VARCHAR(50) DEFAULT 'Vernier/MicrÃ³metro/CMM'
);

-- Columnas de analÃ­tica (por si la tabla ya existÃ­a sin ellas)
ALTER TABLE {ESQUEMA}.revisiones_piezas
    ADD COLUMN IF NOT EXISTS id_herramienta VARCHAR(30),
    ADD COLUMN IF NOT EXISTS piezas_en_herramienta INTEGER,
    ADD COLUMN IF NOT EXISTS temperatura_c NUMERIC(6, 2);

CREATE INDEX IF NOT EXISTS ix_mediciones_revision
    ON {ESQUEMA}.mediciones_detalle(id_revision);
CREATE INDEX IF NOT EXISTS ix_mediciones_cota
    ON {ESQUEMA}.mediciones_detalle(id_cota);
CREATE INDEX IF NOT EXISTS ix_revisiones_pieza
    ON {ESQUEMA}.revisiones_piezas(id_pieza);

-- ------------------------ Trigger de conformidad ---------------------
CREATE OR REPLACE FUNCTION {ESQUEMA}.fn_calcular_conformidad_cota()
RETURNS TRIGGER AS $$
DECLARE
    v_nominal NUMERIC(10, 2);
    v_tol_inf NUMERIC(6, 3);
    v_tol_sup NUMERIC(6, 3);
BEGIN
    SELECT valor_nominal, tolerancia_inferior, tolerancia_superior
    INTO v_nominal, v_tol_inf, v_tol_sup
    FROM {ESQUEMA}.cotas_definicion
    WHERE id_cota = NEW.id_cota;

    IF (NEW.valor_medido >= (v_nominal + v_tol_inf))
       AND (NEW.valor_medido <= (v_nominal + v_tol_sup)) THEN
        NEW.es_conforme := TRUE;
    ELSE
        NEW.es_conforme := FALSE;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_evaluar_medicion ON {ESQUEMA}.mediciones_detalle;
CREATE TRIGGER trg_evaluar_medicion
BEFORE INSERT OR UPDATE ON {ESQUEMA}.mediciones_detalle
FOR EACH ROW
EXECUTE FUNCTION {ESQUEMA}.fn_calcular_conformidad_cota();

-- ------------------------ Vista del cliente --------------------------
CREATE OR REPLACE VIEW {ESQUEMA}.vw_reporte_inspeccion AS
SELECT
    r.id_revision,
    p.nombre_pieza,
    r.numero_serie_pieza,
    r.inspector,
    r.fecha_revision,
    c.codigo_cota,
    c.nombre_caracteristica,
    c.valor_nominal,
    (c.valor_nominal + c.tolerancia_inferior) AS limite_inferior,
    (c.valor_nominal + c.tolerancia_superior) AS limite_superior,
    m.valor_medido,
    CASE WHEN m.es_conforme THEN 'OK' ELSE 'FUERA DE TOLERANCIA' END
        AS estado_dimension
FROM {ESQUEMA}.mediciones_detalle m
JOIN {ESQUEMA}.revisiones_piezas r ON m.id_revision = r.id_revision
JOIN {ESQUEMA}.cotas_definicion c ON m.id_cota = c.id_cota
JOIN {ESQUEMA}.piezas p ON r.id_pieza = p.id_pieza;

-- ------------------------------ Roles -------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pipeline_rw') THEN
        CREATE ROLE pipeline_rw LOGIN PASSWORD 'CAMBIAR_CLAVE_PIPELINE_RW';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'powerbi_ro') THEN
        CREATE ROLE powerbi_ro LOGIN PASSWORD 'CAMBIAR_CLAVE_POWERBI_RO';
    END IF;
END
$$;

GRANT USAGE ON SCHEMA {ESQUEMA} TO pipeline_rw, powerbi_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {ESQUEMA} TO pipeline_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {ESQUEMA} TO pipeline_rw;
GRANT SELECT ON ALL TABLES IN SCHEMA {ESQUEMA} TO powerbi_ro;
GRANT USAGE ON SCHEMA public TO pipeline_rw, powerbi_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO powerbi_ro;

-- --------------------- Vistas para Machine Learning -----------------
DROP VIEW IF EXISTS public.v_entrenamiento_piezas;
DROP VIEW IF EXISTS public.v_riesgo_piezas;

CREATE OR REPLACE VIEW public.v_entrenamiento_piezas AS
SELECT
    p.codigo_pieza,
    r.temperatura_c,
    r.piezas_en_herramienta,
{pivote},
    CASE WHEN r.resultado_general = 'APROBADO' THEN 0 ELSE 1 END AS defectuosa
FROM {ESQUEMA}.revisiones_piezas r
JOIN {ESQUEMA}.piezas p ON p.id_pieza = r.id_pieza
LEFT JOIN {ESQUEMA}.mediciones_detalle m ON m.id_revision = r.id_revision
LEFT JOIN {ESQUEMA}.cotas_definicion c ON c.id_cota = m.id_cota
GROUP BY r.id_revision, p.codigo_pieza, r.temperatura_c,
         r.piezas_en_herramienta, r.resultado_general;

CREATE OR REPLACE VIEW public.v_riesgo_piezas AS
SELECT
    p.codigo_pieza,
    r.temperatura_c,
    r.piezas_en_herramienta,
    EXTRACT(HOUR FROM r.fecha_revision)::int AS hora_dia,
    CASE WHEN r.resultado_general = 'APROBADO' THEN 0 ELSE 1 END AS defectuosa
FROM {ESQUEMA}.revisiones_piezas r
JOIN {ESQUEMA}.piezas p ON p.id_pieza = r.id_pieza;
"""


SQL_PERMISOS_VISTAS = """
-- Permisos sobre las vistas de ML (deben existir antes del GRANT)
GRANT SELECT ON public.v_entrenamiento_piezas, public.v_riesgo_piezas
    TO pipeline_rw, powerbi_ro;
"""


# ---------------------------------------------------------------------------
# Script
# ---------------------------------------------------------------------------
def main() -> int:
    env_salon = SALON / ".env"
    actual = _leer_env(env_salon)

    con = conectar()
    cur = con.cursor()

    print("1. Columnas de analitica ...")
    cur.execute(
        f"""ALTER TABLE {ESQUEMA}.revisiones_piezas
            ADD COLUMN IF NOT EXISTS id_herramienta VARCHAR(30),
            ADD COLUMN IF NOT EXISTS piezas_en_herramienta INTEGER,
            ADD COLUMN IF NOT EXISTS temperatura_c NUMERIC(6,2)"""
    )
    con.commit()

    print("2. Indices ...")
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS ix_mediciones_revision"
        f" ON {ESQUEMA}.mediciones_detalle(id_revision)"
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS ix_mediciones_cota"
        f" ON {ESQUEMA}.mediciones_detalle(id_cota)"
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS ix_revisiones_pieza"
        f" ON {ESQUEMA}.revisiones_piezas(id_pieza)"
    )
    con.commit()

    print("3. Roles ...")
    claves = {
        "PIPELINE_RW_PASSWORD": password_guardada("DB_PASSWORD", actual),
        "POWERBI_RO_PASSWORD": password_guardada("POWERBI_RO_PASSWORD", actual),
    }
    for rol, variable in (
        ("pipeline_rw", "PIPELINE_RW_PASSWORD"),
        ("powerbi_ro", "POWERBI_RO_PASSWORD"),
    ):
        # CREATE ROLE no admite parÃ¡metros enlazados: hay que embeber el
        # literal. Solo se permiten caracteres seguros para evitar inyecciÃ³n.
        clave = claves[variable]
        if not re.fullmatch(r"[A-Za-z0-9_-]{12,}", clave):
            raise SystemExit(f"Clave insegura para {rol}: usa solo letras, nÃºmeros, - y _")
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (rol,))
        if cur.fetchone():
            cur.execute(f"ALTER ROLE {rol} WITH LOGIN PASSWORD '{clave}'")
        else:
            cur.execute(f"CREATE ROLE {rol} WITH LOGIN PASSWORD '{clave}'")
        print(f"   {rol}")
    con.commit()

    print("4. Permisos ...")
    for sentencia in (
        f"GRANT USAGE ON SCHEMA {ESQUEMA} TO pipeline_rw, powerbi_ro",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {ESQUEMA} TO pipeline_rw",
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {ESQUEMA} TO pipeline_rw",
        f"GRANT SELECT ON ALL TABLES IN SCHEMA {ESQUEMA} TO powerbi_ro",
        "GRANT USAGE ON SCHEMA public TO pipeline_rw, powerbi_ro",
        "GRANT SELECT ON ALL TABLES IN SCHEMA public TO powerbi_ro",
    ):
        cur.execute(sentencia)
    con.commit()

    print("5. Vistas de ML ...")
    codigos = leer_cotas(con)
    print(f"   {len(codigos)} cotas")
    # CREATE OR REPLACE VIEW no permite cambiar nombres de columnas.
    cur.execute("DROP VIEW IF EXISTS public.v_entrenamiento_piezas")
    cur.execute("DROP VIEW IF EXISTS public.v_riesgo_piezas")
    con.commit()
    cur.execute(sql_vista_entrenamiento(codigos))
    con.commit()
    cur.execute(SQL_VISTA_RIESGO)
    con.commit()

    # Los permisos se otorgan despuÃ©s de crear las vistas (GRANT ... ON ALL
    # TABLES no alcanza a objetos que aÃºn no existÃ­an).
    cur.execute(
        "GRANT SELECT ON public.v_entrenamiento_piezas, public.v_riesgo_piezas"
        " TO pipeline_rw, powerbi_ro"
    )
    con.commit()

    print("6. Archivo docs/supabase_setup.sql ...")
    (SALON / "docs" / "supabase_setup.sql").write_text(
        sql_setup_completo(codigos) + SQL_PERMISOS_VISTAS, encoding="utf-8"
    )

    print("7. Archivo .env ...")
    cfg = json.loads((PROYECTO / "config" / "base_datos.json").read_text(encoding="utf-8"))
    (SALON / ".env").write_text(
        "\n".join(
            [
                "# Generado por tools/configurar_bd.py -- NO subir a GitHub",
                f"DB_HOST={cfg['host']}",
                f"DB_PORT={cfg['puerto']}",
                f"DB_NAME={cfg['base']}",
                f"DB_USER=pipeline_rw.{cfg['usuario'].split('.')[-1]}",
                f"DB_PASSWORD={claves['PIPELINE_RW_PASSWORD']}",
                f"POWERBI_RO_PASSWORD={claves['POWERBI_RO_PASSWORD']}",
                "DB_SSLMODE=require",
                f"DB_SCHEMA=public",
                "DB_TABLE=v_entrenamiento_piezas",
                "DB_TARGET=defectuosa",
                "INTERVALO_SEGUNDOS=5",
                "POSTGRES_PASSWORD_LOCAL=solo_para_desarrollo_local",
                "",
            ]
        ),
        encoding="utf-8",
    )

    cur.close()
    con.close()
    print("\nListo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
