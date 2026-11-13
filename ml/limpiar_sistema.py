"""
Script para Limpiar y Reiniciar las Tablas de Hechos y Resultados
Conserva intactos los catálogos (dim_piezas, dim_cotas, calidad_piezas.piezas, cotas_definicion)
y vacía las tablas transaccionales de datos simulados, machine learning e IA.
"""

import os
import sys
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ml.conexion_supabase import obtener_engine

def limpiar_base_de_datos():
    engine = obtener_engine()
    
    print("\n" + "=" * 65)
    print(" INICIANDO LIMPIEZA DE TABLAS TRANSACCIONALES EN SUPABASE")
    print("=" * 65)

    with engine.begin() as conn:
        # 1. Limpieza de tablas en esquema calidad_piezas
        print("1. Vaciando calidad_piezas.mediciones_detalle...")
        m_del = conn.execute(text("DELETE FROM calidad_piezas.mediciones_detalle;")).rowcount
        print(f"   Filas eliminadas: {m_del}")

        print("2. Vaciando calidad_piezas.revisiones_piezas...")
        r_del = conn.execute(text("DELETE FROM calidad_piezas.revisiones_piezas;")).rowcount
        print(f"   Filas eliminadas: {r_del}")

        # 2. Limpieza de tablas en esquema public
        print("3. Vaciando public.mediciones...")
        pub_m_del = conn.execute(text("DELETE FROM public.mediciones;")).rowcount
        print(f"   Filas eliminadas: {pub_m_del}")

        print("4. Vaciando public.piezas...")
        pub_p_del = conn.execute(text("DELETE FROM public.piezas;")).rowcount
        print(f"   Filas eliminadas: {pub_p_del}")

        print("5. Vaciando public.flujos...")
        pub_f_del = conn.execute(text("DELETE FROM public.flujos;")).rowcount
        print(f"   Filas eliminadas: {pub_f_del}")

        print("6. Vaciando public.analisis_ia_produccion...")
        pub_ia_del = conn.execute(text("DELETE FROM public.analisis_ia_produccion;")).rowcount
        print(f"   Filas eliminadas: {pub_ia_del}")

        # 3. Reiniciar secuencias de autoincremento
        print("\n7. Reiniciando secuencias de IDs...")
        conn.execute(text("ALTER SEQUENCE IF EXISTS calidad_piezas.revisiones_piezas_id_revision_seq RESTART WITH 1;"))
        conn.execute(text("ALTER SEQUENCE IF EXISTS calidad_piezas.mediciones_detalle_id_medicion_seq RESTART WITH 1;"))
        conn.execute(text("ALTER SEQUENCE IF EXISTS public.analisis_ia_produccion_id_analisis_seq RESTART WITH 1;"))
        print("   Secuencias reiniciadas a 1.")

        # 4. Verificación de estado final
        print("\n" + "=" * 65)
        print(" ESTADO FINAL DE LA BASE DE DATOS:")
        print("=" * 65)
        
        tablas_hechos = [
            ("calidad_piezas", "mediciones_detalle"),
            ("calidad_piezas", "revisiones_piezas"),
            ("public", "mediciones"),
            ("public", "piezas"),
            ("public", "flujos"),
            ("public", "analisis_ia_produccion"),
        ]
        
        for esquema, tabla in tablas_hechos:
            total = conn.execute(text(f'SELECT count(*) FROM "{esquema}"."{tabla}";')).scalar()
            print(f"  • {esquema}.{tabla:25s} : {total} registros (LIMPIO)")

        print("\n CATÁLOGOS CONSERVADOS INTACTOS:")
        tablas_catalogos = [
            ("calidad_piezas", "piezas"),
            ("calidad_piezas", "cotas_definicion"),
            ("public", "dim_piezas"),
            ("public", "dim_cotas"),
        ]
        for esquema, tabla in tablas_catalogos:
            total = conn.execute(text(f'SELECT count(*) FROM "{esquema}"."{tabla}";')).scalar()
            print(f"  • {esquema}.{tabla:25s} : {total} registros (CONSERVADO)")

    print("\n" + "=" * 65)
    print(" ¡SISTEMA LISTO Y REINICIADO PARA UN NUEVO CICLO COMPLETO! ")
    print("=" * 65)

if __name__ == "__main__":
    limpiar_base_de_datos()

