"""
Módulo de Conexión a Base de Datos Supabase (PostgreSQL)
Conecta, descubre e inspecciona tablas para alimentar los modelos de Machine Learning.
"""

import os
import urllib.parse
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, inspect

load_dotenv()


def obtener_engine():
    """Crea y retorna un motor de SQLAlchemy configurado para Supabase."""
    host = os.getenv("SUPABASE_HOST", "aws-0-us-east-2.pooler.supabase.com")
    port = os.getenv("SUPABASE_PORT", "5432")
    database = os.getenv("SUPABASE_DB", "postgres")
    user = os.getenv("SUPABASE_USER", "postgres.abyptuknrvoaadjxkaer")
    password = os.getenv("SUPABASE_PASSWORD", "")

    if not password or password == "TU_CONTRASEÑA_AQUI":
        raise ValueError(
            "⚠️ ATENCIÓN: No has configurado la contraseña de Supabase en el archivo '.env'.\n"
            "Edita el archivo '.env' y reemplaza 'TU_CONTRASEÑA_AQUI' por tu contraseña real."
        )

    # Codificación de usuario y contraseña para caracteres especiales
    password_encoded = urllib.parse.quote_plus(password)
    user_encoded = urllib.parse.quote_plus(user)

    url_conexion = f"postgresql+psycopg2://{user_encoded}:{password_encoded}@{host}:{port}/{database}"
    return create_engine(url_conexion, pool_pre_ping=True)


def listar_tablas_disponibles():
    """Retorna una lista con los nombres de todas las tablas en el esquema 'public'."""
    engine = obtener_engine()
    inspector = inspect(engine)
    tablas = inspector.get_table_names(schema="public")
    return tablas


def inspeccionar_tabla(nombre_tabla: str):
    """Muestra las columnas, tipos de datos y los primeros registros de una tabla de la BD."""
    engine = obtener_engine()
    inspector = inspect(engine)
    columnas = inspector.get_columns(nombre_tabla, schema="public")

    print(f"\n--- Estructura de la tabla '{nombre_tabla}' en Supabase ---")
    for col in columnas:
        print(f"  • {col['name']} ({col['type']})")

    df_muestra = pd.read_sql(f"SELECT * FROM \"{nombre_tabla}\" LIMIT 5;", con=engine)
    print("\nPrimeros 5 registros:")
    print(df_muestra)
    return columnas, df_muestra


def cargar_datos_tabla(nombre_tabla: str) -> pd.DataFrame:
    """Carga todos los datos de la tabla especificada desde Supabase a un DataFrame."""
    engine = obtener_engine()
    query = f"SELECT * FROM \"{nombre_tabla}\";"
    print(f"\nDescargando datos reales de la tabla '{nombre_tabla}' desde Supabase...")
    df = pd.read_sql(query, con=engine)
    print(f"✅ Se cargaron {len(df)} registros y {len(df.columns)} columnas de la base de datos.")
    return df


if __name__ == "__main__":
    try:
        tablas = listar_tablas_disponibles()
        print(f"Tablas encontradas en Supabase: {tablas}")
        if tablas:
            inspeccionar_tabla(tablas[0])
    except Exception as e:
        print(f"Error: {e}")
