"""
Script de Conciliación y Sincronización de Números de Serie en Supabase
Elimina discrepancias entre esquemas y tablas:
1. Elimina registros duplicados en calidad_piezas.revisiones_piezas.
2. Homologa serie_pieza en public.piezas al formato estándar (BASE-001-XXXXXX, etc.).
3. Agrega y puebla serie_pieza en public.mediciones.
4. Sincroniza los flujos, piezas y mediciones del 344 al 1334 en public desde calidad_piezas.
5. Actualiza public.dim_piezas con el código estándar de cliente.
6. Realiza un test de verificación para asegurar 0 discrepancias.
"""

import os
import sys
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ml.conexion_supabase import obtener_engine

MAPEO_CODIGOS = {
    1: ("BAS", "BASE-001"),
    2: ("BR1", "BRZ-001"),
    3: ("CIL", "CIL-001"),
    4: ("CCH", "CCH-001"),
    5: ("EST", "EST-001"),
    6: ("PLM", "PLM-001"),
    7: ("TNS", "TNS-001"),
}

MAPEO_INTERNO_A_CLIENTE = {
    "BAS": "BASE-001",
    "BR1": "BRZ-001",
    "CIL": "CIL-001",
    "CCH": "CCH-001",
    "EST": "EST-001",
    "PLM": "PLM-001",
    "TNS": "TNS-001",
}

def ejecutar_conciliacion():
    engine = obtener_engine()
    
    with engine.begin() as conn:
        print("\n" + "=" * 65)
        print(" PASO 1: Eliminar registros duplicados en calidad_piezas")
        print("=" * 65)
        # 14 IDs de prueba reinsertados el 12 de nov
        res_del = conn.execute(text("""
            DELETE FROM calidad_piezas.revisiones_piezas
            WHERE id_revision IN (13819, 13820, 13821, 13822, 13823, 13824, 13825,
                                 14183, 14184, 14185, 14186, 14187, 14188, 14189);
        """))
        print(f"✅ Filas duplicadas eliminadas en revisiones_piezas: {res_del.rowcount}")

        print("\n" + "=" * 65)
        print(" PASO 2: Homologar formato de serie_pieza en public.piezas")
        print("=" * 65)
        res_upd = conn.execute(text("""
            UPDATE public.piezas
            SET serie_pieza = CASE codigo_pieza
                WHEN 'BAS' THEN 'BASE-001-' || split_part(serie_pieza, '-', 2)
                WHEN 'BR1' THEN 'BRZ-001-'  || split_part(serie_pieza, '-', 2)
                WHEN 'CIL' THEN 'CIL-001-'  || split_part(serie_pieza, '-', 2)
                WHEN 'CCH' THEN 'CCH-001-'  || split_part(serie_pieza, '-', 2)
                WHEN 'EST' THEN 'EST-001-'  || split_part(serie_pieza, '-', 2)
                WHEN 'PLM' THEN 'PLM-001-'  || split_part(serie_pieza, '-', 2)
                WHEN 'TNS' THEN 'TNS-001-'  || split_part(serie_pieza, '-', 2)
                ELSE serie_pieza
            END
            WHERE serie_pieza NOT LIKE '%-001-%';
        """))
        print(f"✅ Series actualizadas en public.piezas: {res_upd.rowcount}")

        print("\n" + "=" * 65)
        print(" PASO 3: Agregar y sincronizar serie_pieza en public.mediciones")
        print("=" * 65)
        conn.execute(text("""
            ALTER TABLE public.mediciones
            ADD COLUMN IF NOT EXISTS serie_pieza VARCHAR(24);
        """))
        res_med = conn.execute(text("""
            UPDATE public.mediciones m
            SET serie_pieza = p.serie_pieza
            FROM public.piezas p
            WHERE m.id_flujo = p.id_flujo
              AND m.codigo_pieza = p.codigo_pieza
              AND (m.serie_pieza IS NULL OR m.serie_pieza != p.serie_pieza);
        """))
        print(f"✅ Mediciones existentes actualizadas con serie_pieza: {res_med.rowcount}")

        print("\n" + "=" * 65)
        print(" PASO 4: Actualizar public.dim_piezas con código de cliente")
        print("=" * 65)
        conn.execute(text("""
            ALTER TABLE public.dim_piezas
            ADD COLUMN IF NOT EXISTS codigo_cliente VARCHAR(10);
        """))
        conn.execute(text("""
            UPDATE public.dim_piezas SET codigo_cliente = 'BASE-001' WHERE codigo_pieza = 'BAS';
            UPDATE public.dim_piezas SET codigo_cliente = 'BRZ-001'  WHERE codigo_pieza = 'BR1';
            UPDATE public.dim_piezas SET codigo_cliente = 'CIL-001'  WHERE codigo_pieza = 'CIL';
            UPDATE public.dim_piezas SET codigo_cliente = 'CCH-001'  WHERE codigo_pieza = 'CCH';
            UPDATE public.dim_piezas SET codigo_cliente = 'EST-001'  WHERE codigo_pieza = 'EST';
            UPDATE public.dim_piezas SET codigo_cliente = 'PLM-001'  WHERE codigo_pieza = 'PLM';
            UPDATE public.dim_piezas SET codigo_cliente = 'TNS-001'  WHERE codigo_pieza = 'TNS';
        """))
        print("✅ Catálogo public.dim_piezas sincronizado con código_cliente.")

        print("\n" + "=" * 65)
        print(" PASO 5: Sincronizar piezas, flujos y mediciones faltantes (344 al 1334)")
        print("=" * 65)
        conn.execute(text("""
            ALTER TABLE public.piezas ALTER COLUMN causa_defecto TYPE TEXT;
            ALTER TABLE public.flujos ALTER COLUMN causa_principal TYPE TEXT;
        """))
        # Insertar flujos faltantes en public.flujos
        res_flujos = conn.execute(text("""
            INSERT INTO public.flujos (
                id_flujo, iniciado_en, cerrado_en, linea, turno, operador,
                lote, piezas_ok, piezas_nok, cotas_nok, causa_principal, estado
            )
            SELECT
                'FL-' || split_part(r.numero_serie_pieza, '-', 3) AS id_flujo,
                MIN(r.fecha_revision) AS iniciado_en,
                MAX(r.fecha_revision) AS cerrado_en,
                'ENSAMBLE-BRAZO' AS linea,
                CASE
                    WHEN EXTRACT(HOUR FROM MIN(r.fecha_revision)) BETWEEN 6 AND 13 THEN 'T1'
                    WHEN EXTRACT(HOUR FROM MIN(r.fecha_revision)) BETWEEN 14 AND 21 THEN 'T2'
                    ELSE 'T3'
                END AS turno,
                MAX(r.inspector) AS operador,
                'L-' || LPAD((split_part(r.numero_serie_pieza, '-', 3)::int / 50 + 1)::text, 4, '0') AS lote,
                SUM(CASE WHEN r.resultado_general = 'APROBADO' THEN 1 ELSE 0 END) AS piezas_ok,
                SUM(CASE WHEN r.resultado_general != 'APROBADO' THEN 1 ELSE 0 END) AS piezas_nok,
                0 AS cotas_nok,
                'sin_defecto' AS causa_principal,
                CASE WHEN SUM(CASE WHEN r.resultado_general != 'APROBADO' THEN 1 ELSE 0 END) = 0 THEN 'OK' ELSE 'NOK' END AS estado
            FROM calidad_piezas.revisiones_piezas r
            WHERE 'FL-' || split_part(r.numero_serie_pieza, '-', 3) NOT IN (SELECT id_flujo FROM public.flujos)
            GROUP BY split_part(r.numero_serie_pieza, '-', 3);
        """))
        print(f"✅ Flujos nuevos insertados en public.flujos: {res_flujos.rowcount}")

        # Insertar piezas faltantes en public.piezas
        res_piezas_nuevas = conn.execute(text("""
            INSERT INTO public.piezas (
                id_flujo, codigo_pieza, serie_pieza, estacion, fabricado_en,
                temperatura_c, id_herramienta, piezas_en_herramienta,
                n_cotas_nok, cotas_nok, causa_defecto, estado
            )
            SELECT
                'FL-' || split_part(r.numero_serie_pieza, '-', 3) AS id_flujo,
                CASE r.id_pieza
                    WHEN 1 THEN 'BAS'
                    WHEN 2 THEN 'BR1'
                    WHEN 3 THEN 'CIL'
                    WHEN 4 THEN 'CCH'
                    WHEN 5 THEN 'EST'
                    WHEN 6 THEN 'PLM'
                    WHEN 7 THEN 'TNS'
                END AS codigo_pieza,
                r.numero_serie_pieza AS serie_pieza,
                CASE r.id_pieza
                    WHEN 1 THEN 'BAS'
                    WHEN 2 THEN 'BR1'
                    WHEN 3 THEN 'CIL'
                    WHEN 4 THEN 'CCH'
                    WHEN 5 THEN 'EST'
                    WHEN 6 THEN 'PLM'
                    WHEN 7 THEN 'TNS'
                END AS estacion,
                r.fecha_revision AS fabricado_en,
                r.temperatura_c,
                COALESCE(r.id_herramienta, 'H-STD-0001') AS id_herramienta,
                COALESCE(r.piezas_en_herramienta, 0) AS piezas_en_herramienta,
                0 AS n_cotas_nok,
                '' AS cotas_nok,
                COALESCE(r.observaciones, 'sin_defecto') AS causa_defecto,
                CASE WHEN r.resultado_general = 'APROBADO' THEN 'OK' ELSE 'NOK' END AS estado
            FROM calidad_piezas.revisiones_piezas r
            WHERE r.numero_serie_pieza NOT IN (SELECT serie_pieza FROM public.piezas);
        """))
        print(f"✅ Piezas nuevas sincronizadas en public.piezas: {res_piezas_nuevas.rowcount}")

        # Insertar mediciones faltantes en public.mediciones
        res_med_nuevas = conn.execute(text("""
            INSERT INTO public.mediciones (
                id_flujo, codigo_pieza, codigo_cota, valor, desviacion, ok, serie_pieza
            )
            SELECT
                'FL-' || split_part(r.numero_serie_pieza, '-', 3) AS id_flujo,
                CASE r.id_pieza
                    WHEN 1 THEN 'BAS'
                    WHEN 2 THEN 'BR1'
                    WHEN 3 THEN 'CIL'
                    WHEN 4 THEN 'CCH'
                    WHEN 5 THEN 'EST'
                    WHEN 6 THEN 'PLM'
                    WHEN 7 THEN 'TNS'
                END AS codigo_pieza,
                c.codigo_cota,
                m.valor_medido AS valor,
                ROUND(m.valor_medido - c.valor_nominal, 4) AS desviacion,
                COALESCE(m.es_conforme, TRUE) AS ok,
                r.numero_serie_pieza AS serie_pieza
            FROM calidad_piezas.mediciones_detalle m
            JOIN calidad_piezas.revisiones_piezas r ON r.id_revision = m.id_revision
            JOIN calidad_piezas.cotas_definicion c ON c.id_cota = m.id_cota
            WHERE r.numero_serie_pieza NOT IN (
                SELECT DISTINCT serie_pieza FROM public.mediciones WHERE serie_pieza IS NOT NULL
            );
        """))
        print(f"✅ Mediciones nuevas sincronizadas en public.mediciones: {res_med_nuevas.rowcount}")

        print("\n" + "=" * 65)
        print(" PASO 6: Validación y verificación de 0 discrepancias")
        print("=" * 65)
        
        # Test 1: Diferencia en números de serie entre piezas y revisiones_piezas
        diff = conn.execute(text("""
            SELECT count(*) 
            FROM public.piezas p
            FULL OUTER JOIN calidad_piezas.revisiones_piezas r
              ON p.serie_pieza = r.numero_serie_pieza
            WHERE p.serie_pieza IS NULL OR r.numero_serie_pieza IS NULL;
        """)).scalar()
        print(f"• Discrepancias entre public.piezas y calidad_piezas.revisiones_piezas: {diff}")

        # Test 2: Mediciones sin serie_pieza
        med_sin_serie = conn.execute(text("""
            SELECT count(*) FROM public.mediciones WHERE serie_pieza IS NULL;
        """)).scalar()
        print(f"• Mediciones en public sin número de serie: {med_sin_serie}")

        # Test 3: Duplicados en calidad_piezas.revisiones_piezas
        dup_calidad = conn.execute(text("""
            SELECT count(*) FROM (
                SELECT numero_serie_pieza FROM calidad_piezas.revisiones_piezas
                GROUP BY numero_serie_pieza HAVING count(*) > 1
            ) s;
        """)).scalar()
        print(f"• Números de serie duplicados en calidad_piezas: {dup_calidad}")

        # Test 4: Duplicados en public.piezas
        dup_public = conn.execute(text("""
            SELECT count(*) FROM (
                SELECT serie_pieza FROM public.piezas
                GROUP BY serie_pieza HAVING count(*) > 1
            ) s;
        """)).scalar()
        print(f"• Números de serie duplicados en public.piezas: {dup_public}")

        total_piezas_p = conn.execute(text("SELECT count(*) FROM public.piezas")).scalar()
        total_piezas_r = conn.execute(text("SELECT count(*) FROM calidad_piezas.revisiones_piezas")).scalar()
        total_med_p = conn.execute(text("SELECT count(*) FROM public.mediciones")).scalar()
        total_med_r = conn.execute(text("SELECT count(*) FROM calidad_piezas.mediciones_detalle")).scalar()

        print("\n" + "=" * 65)
        print(" RESULTADO FINAL DE LA CONCILIACIÓN:")
        print(f"  Total piezas en public.piezas                   : {total_piezas_p}")
        print(f"  Total piezas en calidad_piezas.revisiones_piezas: {total_piezas_r}")
        print(f"  Total mediciones en public.mediciones           : {total_med_p}")
        print(f"  Total mediciones en calidad_piezas.mediciones   : {total_med_r}")
        print("=" * 65)
        if diff == 0 and dup_calidad == 0 and dup_public == 0 and med_sin_serie == 0:
            print("🎉 ¡ÉXITO TOTAL! Todas las tablas concuerdan al 100% sin discrepancias.")
        else:
            print("⚠️ Hay discrepancias pendientes que revisar.")

if __name__ == "__main__":
    ejecutar_conciliacion()
