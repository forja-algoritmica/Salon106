"""Escritura en el esquema `calidad_piezas` (Control de Calidad Dimensional).

Respeta el diseño existente del cliente:

- `piezas` y `cotas_definicion`: catálogo. El programa los sincroniza desde
  `config/catalogo_cotas.csv` (upsert), nunca los borra.
- `revisiones_piezas`: una fila por pieza inspeccionada.
- `mediciones_detalle`: una fila por cota medida. La columna `es_conforme` la
  calcula el trigger del cliente, no este programa.
- `vw_reporte_inspeccion`: vista de reporte, se usa tal cual.

No hay tabla de ensamble en ese esquema, así que el resultado del conjunto y la
causa del defecto viajan en `observaciones` con un formato estable:

    flujo=FL-000012; conjunto=NOK; piezas_nok=1; cotas_nok=BR1-C02; causa=valor_atipico
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from .almacen import AlmacenPostgres
from .config import Config

ESQUEMA = "calidad_piezas"

# Tipo interno (sin acentos) -> valor permitido por el CHECK de la tabla.
TIPO_DB = {
    "lineal": "Lineal",
    "espesor": "Espesor",
    "diametro": "Diámetro",
    "radio": "Radio",
    "angulo": "Ángulo",
}

# Instrumento sugerido según el tipo de cota.
INSTRUMENTO = {
    "lineal": "Cinta métrica / Flexómetro",
    "espesor": "Micrómetro",
    "diametro": "Calibrador Vernier",
    "radio": "CMM",
    "angulo": "Transportador digital",
}

DDL = [
    f"CREATE SCHEMA IF NOT EXISTS {ESQUEMA}",
    f"""
    CREATE TABLE IF NOT EXISTS {ESQUEMA}.piezas (
        id_pieza SERIAL PRIMARY KEY,
        codigo_pieza VARCHAR(50) UNIQUE NOT NULL,
        nombre_pieza VARCHAR(100) NOT NULL,
        descripcion TEXT,
        unidad_medida VARCHAR(10) DEFAULT 'mm',
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {ESQUEMA}.cotas_definicion (
        id_cota SERIAL PRIMARY KEY,
        id_pieza INT NOT NULL REFERENCES {ESQUEMA}.piezas(id_pieza) ON DELETE CASCADE,
        codigo_cota VARCHAR(20) NOT NULL,
        nombre_caracteristica VARCHAR(150) NOT NULL,
        tipo_cota VARCHAR(30) CHECK (
            tipo_cota IN ('Lineal', 'Diámetro', 'Radio', 'Ángulo', 'Espesor')
        ),
        valor_nominal NUMERIC(10, 2) NOT NULL,
        tolerancia_inferior NUMERIC(6, 3) DEFAULT -0.500,
        tolerancia_superior NUMERIC(6, 3) DEFAULT 0.500,
        CONSTRAINT uq_cota_pieza UNIQUE (id_pieza, codigo_cota)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {ESQUEMA}.revisiones_piezas (
        id_revision SERIAL PRIMARY KEY,
        id_pieza INT NOT NULL REFERENCES {ESQUEMA}.piezas(id_pieza),
        numero_serie_pieza VARCHAR(100) NOT NULL,
        inspector VARCHAR(100) NOT NULL,
        fecha_revision TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        resultado_general VARCHAR(20) CHECK (
            resultado_general IN ('APROBADO', 'RECHAZADO', 'REPARACION')
        ),
        observaciones TEXT
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {ESQUEMA}.mediciones_detalle (
        id_medicion SERIAL PRIMARY KEY,
        id_revision INT NOT NULL REFERENCES {ESQUEMA}.revisiones_piezas(id_revision)
            ON DELETE CASCADE,
        id_cota INT NOT NULL REFERENCES {ESQUEMA}.cotas_definicion(id_cota),
        valor_medido NUMERIC(10, 2) NOT NULL,
        es_conforme BOOLEAN,
        instrumento_medicion VARCHAR(50) DEFAULT 'Vernier/Micrómetro/CMM'
    )
    """,
    f"""
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
    $$ LANGUAGE plpgsql
    """,
    f"""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger
            WHERE tgname = 'trg_evaluar_medicion'
              AND tgrelid = '{ESQUEMA}.mediciones_detalle'::regclass
        ) THEN
            CREATE TRIGGER trg_evaluar_medicion
            BEFORE INSERT OR UPDATE ON {ESQUEMA}.mediciones_detalle
            FOR EACH ROW
            EXECUTE FUNCTION {ESQUEMA}.fn_calcular_conformidad_cota();
        END IF;
    END
    $$
    """,
    f"""
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
    JOIN {ESQUEMA}.piezas p ON r.id_pieza = p.id_pieza
    """,
]


def resultado_general(estado: str, causa: str) -> str:
    """Traduce el veredicto interno al CHECK del cliente.

    Una pieza rechazada por un error del instrumento no está confirmada como
    defectuosa: se marca REPARACION para que vuelva a medirse.
    """
    if estado == "OK":
        return "APROBADO"
    if causa == "error_medicion":
        return "REPARACION"
    return "RECHAZADO"


class AlmacenCalidad(AlmacenPostgres):
    """Backend del esquema `calidad_piezas`."""

    nombre = "postgres:calidad_piezas"

    def conectar(self) -> None:
        super().conectar()
        # El trigger del cliente referencia `cotas_definicion` sin calificar,
        # igual que su script original hacía con SET search_path.
        self.ejecutar(f"SET search_path TO {ESQUEMA}, public")

    # -- esquema ------------------------------------------------------------
    def crear_esquema(self, config: Config) -> None:
        if not self._tablas_existen():
            with self.transaccion():
                for sentencia in DDL:
                    self.ejecutar(sentencia)
        self._sincronizar_catalogo(config)

    def _tablas_existen(self) -> bool:
        try:
            cursor = self._ejecutar(
                "SELECT 1 FROM information_schema.tables"
                " WHERE table_schema = %s AND table_name = 'revisiones_piezas'",
                (ESQUEMA,),
            )
            existe = cursor.fetchone() is not None
            cursor.close()
            return existe
        except Exception:
            try:
                self._conexion.rollback()
            except Exception:
                pass
            return False

    def _sincronizar_catalogo(self, config: Config) -> None:
        """Upsert del catálogo. Nunca borra filas existentes."""
        with self.transaccion():
            self._insertar_muchos(
                f"{ESQUEMA}.piezas",
                ["codigo_pieza", "nombre_pieza"],
                [
                    (self.codigo_db(c.codigo), c.nombre)
                    for c in config.componentes
                ],
                "ON CONFLICT (codigo_pieza) DO UPDATE SET"
                " nombre_pieza = EXCLUDED.nombre_pieza",
            )

            mapa = self._mapa_id_pieza()
            filas = []
            for componente in config.componentes:
                id_pieza = mapa[componente.codigo]
                for cota in componente.cotas:
                    filas.append(
                        (
                            id_pieza,
                            cota.codigo,
                            cota.nombre,
                            TIPO_DB[cota.tipo],
                            round(cota.nominal, 2),
                            round(cota.tol_inf, 3),
                            round(cota.tol_sup, 3),
                        )
                    )
            self._insertar_muchos(
                f"{ESQUEMA}.cotas_definicion",
                [
                    "id_pieza",
                    "codigo_cota",
                    "nombre_caracteristica",
                    "tipo_cota",
                    "valor_nominal",
                    "tolerancia_inferior",
                    "tolerancia_superior",
                ],
                filas,
                "ON CONFLICT (id_pieza, codigo_cota) DO UPDATE SET"
                " nombre_caracteristica = EXCLUDED.nombre_caracteristica,"
                " tipo_cota = EXCLUDED.tipo_cota,"
                " valor_nominal = EXCLUDED.valor_nominal,"
                " tolerancia_inferior = EXCLUDED.tolerancia_inferior,"
                " tolerancia_superior = EXCLUDED.tolerancia_superior",
            )
        self._cache_piezas = None
        self._cache_cotas = None

    # -- mapas --------------------------------------------------------------
    def codigo_db(self, codigo_interno: str) -> str:
        return self.mapeo.get(codigo_interno, codigo_interno)

    def _mapa_id_pieza(self) -> dict[str, int]:
        cache = getattr(self, "_cache_piezas", None)
        if cache is not None:
            return cache
        cursor = self._ejecutar(f"SELECT id_pieza, codigo_pieza FROM {ESQUEMA}.piezas")
        por_codigo_db = {str(codigo): int(i) for i, codigo in cursor.fetchall()}
        cursor.close()
        mapa = {
            interno: por_codigo_db[db]
            for interno, db in self.mapeo.items()
            if db in por_codigo_db
        }
        self._cache_piezas = mapa
        return mapa

    def _mapa_id_cota(self, config: Config) -> dict[tuple[str, str], int]:
        cache = getattr(self, "_cache_cotas", None)
        if cache is not None:
            return cache
        cursor = self._ejecutar(
            f"SELECT c.id_cota, p.codigo_pieza, c.codigo_cota"
            f" FROM {ESQUEMA}.cotas_definicion c"
            f" JOIN {ESQUEMA}.piezas p ON p.id_pieza = c.id_pieza"
        )
        por_db = {
            (str(codigo_pieza), str(codigo_cota)): int(id_cota)
            for id_cota, codigo_pieza, codigo_cota in cursor.fetchall()
        }
        cursor.close()
        mapa = {}
        for componente in config.componentes:
            codigo_db = self.codigo_db(componente.codigo)
            for cota in componente.cotas:
                clave = (codigo_db, cota.codigo)
                if clave in por_db:
                    mapa[(componente.codigo, cota.codigo)] = por_db[clave]
        self._cache_cotas = mapa
        return mapa

    # -- escritura ----------------------------------------------------------
    def guardar_flujo(
        self,
        flujo: dict[str, Any],
        piezas: Sequence[dict[str, Any]],
        mediciones: Sequence[dict[str, Any]],
        config: Config | None = None,
    ) -> None:
        if config is None:
            raise ValueError("AlmacenCalidad necesita la configuración del catálogo")
        mapa_piezas = self._mapa_id_pieza()
        mapa_cotas = self._mapa_id_cota(config)

        filas_revision = [
            (
                mapa_piezas[pieza["codigo_pieza"]],
                self.serie_db(pieza["serie_pieza"]),
                flujo["operador"],
                self.adaptar(pieza["fabricado_en"]),
                resultado_general(pieza["estado"], pieza["causa_defecto"]),
                self._observaciones(flujo, pieza),
                pieza["id_herramienta"],
                pieza["piezas_en_herramienta"],
                pieza["temperatura_c"],
            )
            for pieza in piezas
        ]

        por_codigo: dict[str, int] = {}
        with self.transaccion():
            ids = self._insertar_devolviendo(
                f"{ESQUEMA}.revisiones_piezas",
                [
                    "id_pieza",
                    "numero_serie_pieza",
                    "inspector",
                    "fecha_revision",
                    "resultado_general",
                    "observaciones",
                    "id_herramienta",
                    "piezas_en_herramienta",
                    "temperatura_c",
                ],
                filas_revision,
                devolver="id_revision, id_pieza",
            )
            codigo_por_id = {valor: clave for clave, valor in mapa_piezas.items()}
            for id_revision, id_pieza in ids:
                codigo = codigo_por_id.get(int(id_pieza))
                if codigo is not None:
                    por_codigo[codigo] = int(id_revision)

            filas_medicion = []
            for medicion in mediciones:
                id_revision = por_codigo.get(medicion["codigo_pieza"])
                id_cota = mapa_cotas.get(
                    (medicion["codigo_pieza"], medicion["codigo_cota"])
                )
                if id_revision is None or id_cota is None:
                    continue
                filas_medicion.append(
                    (
                        id_revision,
                        id_cota,
                        round(float(medicion["valor"]), 2),
                        self._instrumento(medicion["codigo_cota"], config),
                    )
                )

            self._insertar_muchos(
                f"{ESQUEMA}.mediciones_detalle",
                ["id_revision", "id_cota", "valor_medido", "instrumento_medicion"],
                filas_medicion,
            )

    # -- utilidades ---------------------------------------------------------
    def serie_db(self, serie_interna: str) -> str:
        """'BAS-000012' -> 'BASE-001-000012'."""
        codigo, _, consecutivo = serie_interna.rpartition("-")
        return f"{self.codigo_db(codigo)}-{consecutivo}"

    def reiniciar_hechos(self) -> dict[str, int]:
        """Vacía las tablas de hechos y conserva el catálogo.

        Útil cuando los datos de prueba quedaron con fechas futuras o se quiere
        empezar un tablero limpio. No toca `piezas` ni `cotas_definicion`.
        """
        with self.transaccion():
            cursor = self._ejecutar(f"DELETE FROM {ESQUEMA}.mediciones_detalle")
            mediciones = cursor.rowcount
            cursor.close()
            cursor = self._ejecutar(f"DELETE FROM {ESQUEMA}.revisiones_piezas")
            revisiones = cursor.rowcount
            cursor.close()
        return {"mediciones": int(mediciones), "revisiones": int(revisiones)}

    def limpiar_catalogos(self, config: Config) -> int:
        """Borra cotas de definición que no están en el catálogo y no se usan."""
        mapa = self._mapa_id_pieza()
        validas = {
            (mapa[componente.codigo], cota.codigo)
            for componente in config.componentes
            for cota in componente.cotas
            if componente.codigo in mapa
        }

        cursor = self._ejecutar(
            f"SELECT id_cota, id_pieza, codigo_cota FROM {ESQUEMA}.cotas_definicion"
        )
        filas = cursor.fetchall()
        cursor.close()

        sobrantes = [
            int(id_cota)
            for id_cota, id_pieza, codigo_cota in filas
            if (int(id_pieza), str(codigo_cota)) not in validas
        ]
        if not sobrantes:
            return 0

        lista = ", ".join(str(int(i)) for i in sobrantes)
        self.ejecutar(
            f"DELETE FROM {ESQUEMA}.cotas_definicion c"
            f" WHERE c.id_cota IN ({lista})"
            f" AND NOT EXISTS (SELECT 1 FROM {ESQUEMA}.mediciones_detalle m"
            " WHERE m.id_cota = c.id_cota)"
        )
        return len(sobrantes)

    @staticmethod
    def _observaciones(flujo: dict[str, Any], pieza: dict[str, Any]) -> str:
        return (
            f"flujo={flujo['id_flujo']}; conjunto={flujo['estado']};"
            f" piezas_nok={flujo['piezas_nok']};"
            f" cotas_nok={pieza['cotas_nok'] or '-'};"
            f" causa={pieza['causa_defecto']}"
        )

    def _instrumento(self, codigo_cota: str, config: Config) -> str:
        for componente in config.componentes:
            for cota in componente.cotas:
                if cota.codigo == codigo_cota:
                    return INSTRUMENTO.get(cota.tipo, "Vernier")
        return "Vernier"

    # -- continuación -------------------------------------------------------
    def _total_revisiones(self) -> int:
        cursor = self._ejecutar(f"SELECT COUNT(*) FROM {ESQUEMA}.revisiones_piezas")
        total = int(cursor.fetchone()[0])
        cursor.close()
        return total

    def ultimo_flujo(self) -> int:
        """Los flujos se deducen de las revisiones: 7 piezas por ensamble."""
        return self._total_revisiones() // max(len(self.mapeo), 1)

    def contadores_piezas(self) -> dict[str, int]:
        cursor = self._ejecutar(
            f"SELECT p.codigo_pieza, COUNT(*) FROM {ESQUEMA}.revisiones_piezas r"
            f" JOIN {ESQUEMA}.piezas p ON p.id_pieza = r.id_pieza"
            " GROUP BY p.codigo_pieza"
        )
        por_db = {str(c): int(n) for c, n in cursor.fetchall()}
        cursor.close()
        return {
            interno: por_db[db]
            for interno, db in self.mapeo.items()
            if db in por_db
        }

    def ultimo_cierre(self) -> datetime | None:
        cursor = self._ejecutar(
            f"SELECT MAX(fecha_revision) FROM {ESQUEMA}.revisiones_piezas"
        )
        valor = cursor.fetchone()[0]
        cursor.close()
        if valor is None:
            return None
        return valor if isinstance(valor, datetime) else datetime.fromisoformat(str(valor))

    def resumen_estado(self) -> dict[str, Any]:
        revisiones = self._total_revisiones()
        flujos = revisiones // max(len(self.mapeo), 1)

        cursor = self._ejecutar(
            f"SELECT resultado_general, COUNT(*) FROM {ESQUEMA}.revisiones_piezas"
            " GROUP BY resultado_general"
        )
        por_resultado = {str(r): int(n) for r, n in cursor.fetchall()}
        cursor.close()

        cursor = self._ejecutar(
            f"SELECT COUNT(*) FROM {ESQUEMA}.mediciones_detalle"
        )
        mediciones = int(cursor.fetchone()[0])
        cursor.close()

        cursor = self._ejecutar(
            f"SELECT COUNT(*) FROM {ESQUEMA}.cotas_definicion"
        )
        cotas_definidas = int(cursor.fetchone()[0])
        cursor.close()

        cursor = self._ejecutar(
            f"SELECT substring(observaciones from 'causa=([a-z_]+)') AS causa,"
            f" COUNT(*) FROM {ESQUEMA}.revisiones_piezas"
            " WHERE resultado_general <> 'APROBADO'"
            f" AND observaciones LIKE '%causa=%'"
            " GROUP BY 1 ORDER BY 2 DESC"
        )
        causas = [(str(c), int(n)) for c, n in cursor.fetchall()]
        cursor.close()

        cursor = self._ejecutar(
            f"SELECT c.codigo_cota, COUNT(*) FROM {ESQUEMA}.mediciones_detalle m"
            f" JOIN {ESQUEMA}.cotas_definicion c ON c.id_cota = m.id_cota"
            " WHERE m.es_conforme = FALSE"
            " GROUP BY c.codigo_cota ORDER BY 2 DESC LIMIT 5"
        )
        cotas = [(str(c), int(n)) for c, n in cursor.fetchall()]
        cursor.close()

        return {
            "flujos": flujos,
            "piezas": revisiones,
            "mediciones": mediciones,
            "cotas_definidas": cotas_definidas,
            "piezas_ok": por_resultado.get("APROBADO", 0),
            "piezas_nok": por_resultado.get("RECHAZADO", 0),
            "reparacion": por_resultado.get("REPARACION", 0),
            "causas": causas,
            "cotas_criticas": cotas,
            "ultimo_flujo": flujos,
            "ultimo_cierre": self.ultimo_cierre(),
        }
