-- =====================================================================
-- Setup de base de datos â€” Control de Calidad Dimensional + ML
-- Generado por tools/configurar_bd.py
--
-- Ejecutar completo en Supabase -> SQL Editor.
-- ANTES de ejecutarlo, cambia las dos contraseÃ±as marcadas como CAMBIAR.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS calidad_piezas;
SET search_path TO calidad_piezas, public;

-- ------------------------------ Tablas ------------------------------
CREATE TABLE IF NOT EXISTS calidad_piezas.piezas (
    id_pieza SERIAL PRIMARY KEY,
    codigo_pieza VARCHAR(50) UNIQUE NOT NULL,
    nombre_pieza VARCHAR(100) NOT NULL,
    descripcion TEXT,
    unidad_medida VARCHAR(10) DEFAULT 'mm',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS calidad_piezas.cotas_definicion (
    id_cota SERIAL PRIMARY KEY,
    id_pieza INT NOT NULL REFERENCES calidad_piezas.piezas(id_pieza) ON DELETE CASCADE,
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

CREATE TABLE IF NOT EXISTS calidad_piezas.revisiones_piezas (
    id_revision SERIAL PRIMARY KEY,
    id_pieza INT NOT NULL REFERENCES calidad_piezas.piezas(id_pieza),
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

CREATE TABLE IF NOT EXISTS calidad_piezas.mediciones_detalle (
    id_medicion SERIAL PRIMARY KEY,
    id_revision INT NOT NULL REFERENCES calidad_piezas.revisiones_piezas(id_revision)
        ON DELETE CASCADE,
    id_cota INT NOT NULL REFERENCES calidad_piezas.cotas_definicion(id_cota),
    valor_medido NUMERIC(10, 2) NOT NULL,
    es_conforme BOOLEAN,
    instrumento_medicion VARCHAR(50) DEFAULT 'Vernier/MicrÃ³metro/CMM'
);

-- Columnas de analÃ­tica (por si la tabla ya existÃ­a sin ellas)
ALTER TABLE calidad_piezas.revisiones_piezas
    ADD COLUMN IF NOT EXISTS id_herramienta VARCHAR(30),
    ADD COLUMN IF NOT EXISTS piezas_en_herramienta INTEGER,
    ADD COLUMN IF NOT EXISTS temperatura_c NUMERIC(6, 2);

CREATE INDEX IF NOT EXISTS ix_mediciones_revision
    ON calidad_piezas.mediciones_detalle(id_revision);
CREATE INDEX IF NOT EXISTS ix_mediciones_cota
    ON calidad_piezas.mediciones_detalle(id_cota);
CREATE INDEX IF NOT EXISTS ix_revisiones_pieza
    ON calidad_piezas.revisiones_piezas(id_pieza);

-- ------------------------ Trigger de conformidad ---------------------
CREATE OR REPLACE FUNCTION calidad_piezas.fn_calcular_conformidad_cota()
RETURNS TRIGGER AS $$
DECLARE
    v_nominal NUMERIC(10, 2);
    v_tol_inf NUMERIC(6, 3);
    v_tol_sup NUMERIC(6, 3);
BEGIN
    SELECT valor_nominal, tolerancia_inferior, tolerancia_superior
    INTO v_nominal, v_tol_inf, v_tol_sup
    FROM calidad_piezas.cotas_definicion
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

DROP TRIGGER IF EXISTS trg_evaluar_medicion ON calidad_piezas.mediciones_detalle;
CREATE TRIGGER trg_evaluar_medicion
BEFORE INSERT OR UPDATE ON calidad_piezas.mediciones_detalle
FOR EACH ROW
EXECUTE FUNCTION calidad_piezas.fn_calcular_conformidad_cota();

-- ------------------------ Vista del cliente --------------------------
CREATE OR REPLACE VIEW calidad_piezas.vw_reporte_inspeccion AS
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
FROM calidad_piezas.mediciones_detalle m
JOIN calidad_piezas.revisiones_piezas r ON m.id_revision = r.id_revision
JOIN calidad_piezas.cotas_definicion c ON m.id_cota = c.id_cota
JOIN calidad_piezas.piezas p ON r.id_pieza = p.id_pieza;

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

GRANT USAGE ON SCHEMA calidad_piezas TO pipeline_rw, powerbi_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA calidad_piezas TO pipeline_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA calidad_piezas TO pipeline_rw;
GRANT SELECT ON ALL TABLES IN SCHEMA calidad_piezas TO powerbi_ro;
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
        MAX(CASE WHEN c.codigo_cota = 'BAS-C01' THEN m.valor_medido END) AS cota_bas_c01,
        MAX(CASE WHEN c.codigo_cota = 'BAS-C02' THEN m.valor_medido END) AS cota_bas_c02,
        MAX(CASE WHEN c.codigo_cota = 'BAS-C03' THEN m.valor_medido END) AS cota_bas_c03,
        MAX(CASE WHEN c.codigo_cota = 'BAS-C04' THEN m.valor_medido END) AS cota_bas_c04,
        MAX(CASE WHEN c.codigo_cota = 'BAS-C05' THEN m.valor_medido END) AS cota_bas_c05,
        MAX(CASE WHEN c.codigo_cota = 'BAS-C06' THEN m.valor_medido END) AS cota_bas_c06,
        MAX(CASE WHEN c.codigo_cota = 'BAS-C07' THEN m.valor_medido END) AS cota_bas_c07,
        MAX(CASE WHEN c.codigo_cota = 'BAS-C08' THEN m.valor_medido END) AS cota_bas_c08,
        MAX(CASE WHEN c.codigo_cota = 'BAS-C09' THEN m.valor_medido END) AS cota_bas_c09,
        MAX(CASE WHEN c.codigo_cota = 'BAS-C10' THEN m.valor_medido END) AS cota_bas_c10,
        MAX(CASE WHEN c.codigo_cota = 'BAS-C11' THEN m.valor_medido END) AS cota_bas_c11,
        MAX(CASE WHEN c.codigo_cota = 'BAS-C12' THEN m.valor_medido END) AS cota_bas_c12,
        MAX(CASE WHEN c.codigo_cota = 'BAS-C13' THEN m.valor_medido END) AS cota_bas_c13,
        MAX(CASE WHEN c.codigo_cota = 'BAS-C14' THEN m.valor_medido END) AS cota_bas_c14,
        MAX(CASE WHEN c.codigo_cota = 'BAS-C15' THEN m.valor_medido END) AS cota_bas_c15,
        MAX(CASE WHEN c.codigo_cota = 'BAS-C16' THEN m.valor_medido END) AS cota_bas_c16,
        MAX(CASE WHEN c.codigo_cota = 'BR1-C01' THEN m.valor_medido END) AS cota_br1_c01,
        MAX(CASE WHEN c.codigo_cota = 'BR1-C02' THEN m.valor_medido END) AS cota_br1_c02,
        MAX(CASE WHEN c.codigo_cota = 'BR1-C03' THEN m.valor_medido END) AS cota_br1_c03,
        MAX(CASE WHEN c.codigo_cota = 'BR1-C04' THEN m.valor_medido END) AS cota_br1_c04,
        MAX(CASE WHEN c.codigo_cota = 'BR1-C05' THEN m.valor_medido END) AS cota_br1_c05,
        MAX(CASE WHEN c.codigo_cota = 'BR1-C06' THEN m.valor_medido END) AS cota_br1_c06,
        MAX(CASE WHEN c.codigo_cota = 'BR1-C07' THEN m.valor_medido END) AS cota_br1_c07,
        MAX(CASE WHEN c.codigo_cota = 'BR1-C08' THEN m.valor_medido END) AS cota_br1_c08,
        MAX(CASE WHEN c.codigo_cota = 'BR1-C09' THEN m.valor_medido END) AS cota_br1_c09,
        MAX(CASE WHEN c.codigo_cota = 'BR1-C10' THEN m.valor_medido END) AS cota_br1_c10,
        MAX(CASE WHEN c.codigo_cota = 'BR1-C11' THEN m.valor_medido END) AS cota_br1_c11,
        MAX(CASE WHEN c.codigo_cota = 'BR1-C12' THEN m.valor_medido END) AS cota_br1_c12,
        MAX(CASE WHEN c.codigo_cota = 'BR1-C13' THEN m.valor_medido END) AS cota_br1_c13,
        MAX(CASE WHEN c.codigo_cota = 'BR1-C14' THEN m.valor_medido END) AS cota_br1_c14,
        MAX(CASE WHEN c.codigo_cota = 'CIL-C01' THEN m.valor_medido END) AS cota_cil_c01,
        MAX(CASE WHEN c.codigo_cota = 'CIL-C02' THEN m.valor_medido END) AS cota_cil_c02,
        MAX(CASE WHEN c.codigo_cota = 'CIL-C03' THEN m.valor_medido END) AS cota_cil_c03,
        MAX(CASE WHEN c.codigo_cota = 'CIL-C04' THEN m.valor_medido END) AS cota_cil_c04,
        MAX(CASE WHEN c.codigo_cota = 'CIL-C05' THEN m.valor_medido END) AS cota_cil_c05,
        MAX(CASE WHEN c.codigo_cota = 'CIL-C06' THEN m.valor_medido END) AS cota_cil_c06,
        MAX(CASE WHEN c.codigo_cota = 'CIL-C07' THEN m.valor_medido END) AS cota_cil_c07,
        MAX(CASE WHEN c.codigo_cota = 'CIL-C08' THEN m.valor_medido END) AS cota_cil_c08,
        MAX(CASE WHEN c.codigo_cota = 'CIL-C09' THEN m.valor_medido END) AS cota_cil_c09,
        MAX(CASE WHEN c.codigo_cota = 'CIL-C10' THEN m.valor_medido END) AS cota_cil_c10,
        MAX(CASE WHEN c.codigo_cota = 'CCH-C01' THEN m.valor_medido END) AS cota_cch_c01,
        MAX(CASE WHEN c.codigo_cota = 'CCH-C02' THEN m.valor_medido END) AS cota_cch_c02,
        MAX(CASE WHEN c.codigo_cota = 'CCH-C03' THEN m.valor_medido END) AS cota_cch_c03,
        MAX(CASE WHEN c.codigo_cota = 'CCH-C04' THEN m.valor_medido END) AS cota_cch_c04,
        MAX(CASE WHEN c.codigo_cota = 'CCH-C05' THEN m.valor_medido END) AS cota_cch_c05,
        MAX(CASE WHEN c.codigo_cota = 'CCH-C06' THEN m.valor_medido END) AS cota_cch_c06,
        MAX(CASE WHEN c.codigo_cota = 'CCH-C07' THEN m.valor_medido END) AS cota_cch_c07,
        MAX(CASE WHEN c.codigo_cota = 'CCH-C08' THEN m.valor_medido END) AS cota_cch_c08,
        MAX(CASE WHEN c.codigo_cota = 'CCH-C09' THEN m.valor_medido END) AS cota_cch_c09,
        MAX(CASE WHEN c.codigo_cota = 'CCH-C10' THEN m.valor_medido END) AS cota_cch_c10,
        MAX(CASE WHEN c.codigo_cota = 'CCH-C11' THEN m.valor_medido END) AS cota_cch_c11,
        MAX(CASE WHEN c.codigo_cota = 'CCH-C12' THEN m.valor_medido END) AS cota_cch_c12,
        MAX(CASE WHEN c.codigo_cota = 'EST-C01' THEN m.valor_medido END) AS cota_est_c01,
        MAX(CASE WHEN c.codigo_cota = 'EST-C02' THEN m.valor_medido END) AS cota_est_c02,
        MAX(CASE WHEN c.codigo_cota = 'EST-C03' THEN m.valor_medido END) AS cota_est_c03,
        MAX(CASE WHEN c.codigo_cota = 'EST-C04' THEN m.valor_medido END) AS cota_est_c04,
        MAX(CASE WHEN c.codigo_cota = 'EST-C05' THEN m.valor_medido END) AS cota_est_c05,
        MAX(CASE WHEN c.codigo_cota = 'EST-C06' THEN m.valor_medido END) AS cota_est_c06,
        MAX(CASE WHEN c.codigo_cota = 'EST-C07' THEN m.valor_medido END) AS cota_est_c07,
        MAX(CASE WHEN c.codigo_cota = 'EST-C08' THEN m.valor_medido END) AS cota_est_c08,
        MAX(CASE WHEN c.codigo_cota = 'PLM-C01' THEN m.valor_medido END) AS cota_plm_c01,
        MAX(CASE WHEN c.codigo_cota = 'PLM-C02' THEN m.valor_medido END) AS cota_plm_c02,
        MAX(CASE WHEN c.codigo_cota = 'PLM-C03' THEN m.valor_medido END) AS cota_plm_c03,
        MAX(CASE WHEN c.codigo_cota = 'PLM-C04' THEN m.valor_medido END) AS cota_plm_c04,
        MAX(CASE WHEN c.codigo_cota = 'PLM-C05' THEN m.valor_medido END) AS cota_plm_c05,
        MAX(CASE WHEN c.codigo_cota = 'PLM-C06' THEN m.valor_medido END) AS cota_plm_c06,
        MAX(CASE WHEN c.codigo_cota = 'PLM-C07' THEN m.valor_medido END) AS cota_plm_c07,
        MAX(CASE WHEN c.codigo_cota = 'PLM-C08' THEN m.valor_medido END) AS cota_plm_c08,
        MAX(CASE WHEN c.codigo_cota = 'PLM-C09' THEN m.valor_medido END) AS cota_plm_c09,
        MAX(CASE WHEN c.codigo_cota = 'PLM-C10' THEN m.valor_medido END) AS cota_plm_c10,
        MAX(CASE WHEN c.codigo_cota = 'PLM-C11' THEN m.valor_medido END) AS cota_plm_c11,
        MAX(CASE WHEN c.codigo_cota = 'PLM-C12' THEN m.valor_medido END) AS cota_plm_c12,
        MAX(CASE WHEN c.codigo_cota = 'PLM-C13' THEN m.valor_medido END) AS cota_plm_c13,
        MAX(CASE WHEN c.codigo_cota = 'PLM-C14' THEN m.valor_medido END) AS cota_plm_c14,
        MAX(CASE WHEN c.codigo_cota = 'PLM-C15' THEN m.valor_medido END) AS cota_plm_c15,
        MAX(CASE WHEN c.codigo_cota = 'PLM-C16' THEN m.valor_medido END) AS cota_plm_c16,
        MAX(CASE WHEN c.codigo_cota = 'TNS-C01' THEN m.valor_medido END) AS cota_tns_c01,
        MAX(CASE WHEN c.codigo_cota = 'TNS-C02' THEN m.valor_medido END) AS cota_tns_c02,
        MAX(CASE WHEN c.codigo_cota = 'TNS-C03' THEN m.valor_medido END) AS cota_tns_c03,
        MAX(CASE WHEN c.codigo_cota = 'TNS-C04' THEN m.valor_medido END) AS cota_tns_c04,
        MAX(CASE WHEN c.codigo_cota = 'TNS-C05' THEN m.valor_medido END) AS cota_tns_c05,
        MAX(CASE WHEN c.codigo_cota = 'TNS-C06' THEN m.valor_medido END) AS cota_tns_c06,
    CASE WHEN r.resultado_general = 'APROBADO' THEN 0 ELSE 1 END AS defectuosa
FROM calidad_piezas.revisiones_piezas r
JOIN calidad_piezas.piezas p ON p.id_pieza = r.id_pieza
LEFT JOIN calidad_piezas.mediciones_detalle m ON m.id_revision = r.id_revision
LEFT JOIN calidad_piezas.cotas_definicion c ON c.id_cota = m.id_cota
GROUP BY r.id_revision, p.codigo_pieza, r.temperatura_c,
         r.piezas_en_herramienta, r.resultado_general;

CREATE OR REPLACE VIEW public.v_riesgo_piezas AS
SELECT
    p.codigo_pieza,
    r.temperatura_c,
    r.piezas_en_herramienta,
    EXTRACT(HOUR FROM r.fecha_revision)::int AS hora_dia,
    CASE WHEN r.resultado_general = 'APROBADO' THEN 0 ELSE 1 END AS defectuosa
FROM calidad_piezas.revisiones_piezas r
JOIN calidad_piezas.piezas p ON p.id_pieza = r.id_pieza;

CREATE OR REPLACE VIEW public.v_decisiones AS
SELECT d.id_decision, d.id_revision, p.codigo_pieza, r.fecha_revision,
       r.resultado_general, d.probabilidad, d.umbral, d.decision,
       d.motivo, d.modelo, d.generado_en
FROM calidad_piezas.decisiones d
JOIN calidad_piezas.revisiones_piezas r ON r.id_revision = d.id_revision
JOIN calidad_piezas.piezas p ON p.id_pieza = r.id_pieza;

-- Permisos sobre las vistas de ML (deben existir antes del GRANT)
GRANT SELECT ON public.v_entrenamiento_piezas, public.v_riesgo_piezas,
    public.v_decisiones TO pipeline_rw, powerbi_ro;
