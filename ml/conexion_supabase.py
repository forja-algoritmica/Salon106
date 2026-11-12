"""Conexión a Supabase (PostgreSQL) para el equipo de ML.

Sin dependencias compiladas: `pg8000` (Python puro) y `numpy`.

Motivo: en equipos con políticas de control de aplicaciones (WDAC) las
extensiones compiladas de pandas, SQLAlchemy o psycopg quedan bloqueadas. Esta
versión funciona igual en Windows restringido y dentro del contenedor Linux.

Variables de entorno (`.env` en la raíz del repo):

    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
    DB_SCHEMA   (por defecto 'public')
    DB_TABLE    (tabla o vista por defecto)
    DB_TARGET   (columna objetivo)
"""

from __future__ import annotations

import os
import ssl
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    _env = Path(__file__).resolve().parent.parent / ".env"
    if _env.exists():
        for _linea in _env.read_text(encoding="utf-8").splitlines():
            _linea = _linea.strip()
            if _linea and not _linea.startswith("#") and "=" in _linea:
                _clave, _valor = _linea.split("=", 1)
                os.environ.setdefault(_clave.strip(), _valor.strip())


# ---------------------------------------------------------------------------
# Tabla en memoria (sustituye a pandas.DataFrame)
# ---------------------------------------------------------------------------
@dataclass
class Tabla:
    """Columnas y filas de una consulta, sin dependencias externas."""

    columnas: list[str] = field(default_factory=list)
    filas: list[tuple] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.filas)

    @property
    def forma(self) -> tuple[int, int]:
        return len(self.filas), len(self.columnas)

    def columna(self, nombre: str) -> list:
        i = self.columnas.index(nombre)
        return [fila[i] for fila in self.filas]

    def primeras(self, n: int = 5) -> list[tuple]:
        return self.filas[:n]

    def __repr__(self) -> str:
        return f"Tabla({len(self.filas)} filas x {len(self.columnas)} columnas)"


def _ajuste(nombre: str, defecto: str = "") -> str:
    """Lee DB_* y, si no existe, cae a SUPABASE_* (compatibilidad)."""
    return os.getenv(nombre) or os.getenv(nombre.replace("DB_", "SUPABASE_")) or defecto


def obtener_parametros() -> dict:
    host = _ajuste("DB_HOST")
    usuario = _ajuste("DB_USER")
    clave = _ajuste("DB_PASSWORD")

    if not host or not usuario:
        raise ValueError(
            "Faltan datos de conexión. Copia .env.example a .env y completa "
            "DB_HOST, DB_USER y DB_PASSWORD."
        )
    if not clave or clave == "TU_CONTRASEÑA_AQUI":
        raise ValueError("Falta la contraseña. Escribe DB_PASSWORD en el archivo .env.")

    return {
        "host": host,
        "port": int(_ajuste("DB_PORT", "5432")),
        "database": _ajuste("DB_NAME", "postgres"),
        "user": usuario,
        "password": clave,
        "schema": _ajuste("DB_SCHEMA", "public"),
    }


def obtener_conexion():
    import pg8000.dbapi

    params = obtener_parametros()
    contexto = ssl.create_default_context()
    contexto.check_hostname = False
    contexto.verify_mode = ssl.CERT_NONE
    return pg8000.dbapi.connect(
        host=params["host"],
        port=params["port"],
        database=params["database"],
        user=params["user"],
        password=params["password"],
        timeout=30,
        ssl_context=contexto,
    )


def consultar(sql: str, parametros: tuple = ()) -> Tabla:
    con = obtener_conexion()
    try:
        cur = con.cursor()
        cur.execute(sql, parametros)
        columnas = [d[0] for d in cur.description]
        filas = cur.fetchall()
        cur.close()
    finally:
        con.close()
    return Tabla(columnas=columnas, filas=[tuple(f) for f in filas])


def listar_tablas_disponibles(schema: str | None = None) -> list[str]:
    schema = schema or obtener_parametros()["schema"]
    tabla = consultar(
        "SELECT table_name FROM information_schema.tables"
        " WHERE table_schema = %s AND table_type IN ('BASE TABLE', 'VIEW')"
        " ORDER BY table_name",
        (schema,),
    )
    return [str(f[0]) for f in tabla.filas]


def inspeccionar_tabla(nombre_tabla: str, schema: str | None = None) -> Tabla:
    schema = schema or obtener_parametros()["schema"]
    columnas = consultar(
        "SELECT column_name, data_type FROM information_schema.columns"
        " WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
        (schema, nombre_tabla),
    )
    print(f"\n--- Estructura de {schema}.{nombre_tabla} ---")
    for nombre, tipo in columnas.filas:
        print(f"  • {nombre} ({tipo})")

    muestra = consultar(f'SELECT * FROM "{schema}"."{nombre_tabla}" LIMIT 5')
    print("\nPrimeras 5 filas:")
    for fila in muestra.primeras():
        print("  ", fila)
    return muestra


def cargar_datos_tabla(nombre_tabla: str, schema: str | None = None) -> Tabla:
    schema = schema or obtener_parametros()["schema"]
    print(f"\nDescargando {schema}.{nombre_tabla} ...")
    tabla = consultar(f'SELECT * FROM "{schema}"."{nombre_tabla}"')
    print(f"Se cargaron {len(tabla)} registros y {len(tabla.columnas)} columnas.")
    return tabla


def tabla_por_defecto() -> str:
    return os.getenv("DB_TABLE") or "v_entrenamiento_piezas"


if __name__ == "__main__":
    try:
        objetos = listar_tablas_disponibles()
        print(f"Objetos en el esquema: {objetos}")
        if objetos:
            inspeccionar_tabla(objetos[0])
    except Exception as error:  # pragma: no cover
        print(f"Error: {error}")
