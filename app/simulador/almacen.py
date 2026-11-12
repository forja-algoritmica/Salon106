"""Acceso a base de datos: Postgres (Supabase) o SQLite local.

Se usa `pg8000`, que es Python puro: no necesita DLLs y por eso se empaqueta
sin problemas dentro de un .exe. SQLite queda disponible para trabajar sin
internet o para pruebas.

Las credenciales NUNCA viven en el código. La contraseña se lee de la variable
de entorno ENSAMBLE_DB_PASSWORD o del archivo `config/.env`.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from .config import Config

VARIABLE_PASSWORD = "ENSAMBLE_DB_PASSWORD"


# ---------------------------------------------------------------------------
# Parámetros de conexión
# ---------------------------------------------------------------------------
@dataclass
class BaseDatos:
    motor: str = "ninguno"  # postgres | sqlite | ninguno
    host: str = ""
    puerto: int = 5432
    base: str = "postgres"
    usuario: str = ""
    sslmode: str = "require"
    archivo_sqlite: str = "datos/linea.db"
    estructura: str = "calidad"  # calidad (esquema del cliente) | propio
    esquema: str = "calidad_piezas"
    mapeo_piezas: dict[str, str] = field(default_factory=dict)

    def __repr__(self) -> str:  # nunca mostrar secretos
        if self.motor == "postgres":
            return (
                f"BaseDatos(postgres {self.usuario}@{self.host}:{self.puerto}"
                f"/{self.base} esquema={self.esquema})"
            )
        return f"BaseDatos({self.motor})"


def leer_env(ruta: Path) -> dict[str, str]:
    """Lector mínimo de archivos .env (CLAVE=valor)."""
    valores: dict[str, str] = {}
    if not ruta.exists():
        return valores
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        valores[clave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def resolver_password(carpeta_config: Path) -> str | None:
    """Busca la contraseña en el entorno y luego en config/.env."""
    if os.environ.get(VARIABLE_PASSWORD):
        return os.environ[VARIABLE_PASSWORD]
    # Integración con el repo: el .env del proyecto usa DB_PASSWORD.
    if os.environ.get("DB_PASSWORD"):
        return os.environ["DB_PASSWORD"]
    return leer_env(carpeta_config / ".env").get(VARIABLE_PASSWORD)


# ---------------------------------------------------------------------------
# Esquema
# ---------------------------------------------------------------------------
DDL = [
    """
    CREATE TABLE IF NOT EXISTS dim_piezas (
        id_pieza       INTEGER PRIMARY KEY,
        codigo_pieza   VARCHAR(8)  NOT NULL,
        nombre_pieza   VARCHAR(60) NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim_cotas (
        codigo_cota      VARCHAR(12) PRIMARY KEY,
        id_pieza         INTEGER      NOT NULL,
        codigo_pieza     VARCHAR(8)   NOT NULL,
        nombre_cota      VARCHAR(90)  NOT NULL,
        tipo             VARCHAR(10)  NOT NULL,
        unidad           VARCHAR(4)   NOT NULL,
        nominal          NUMERIC(12,4) NOT NULL,
        limite_inferior  NUMERIC(12,4) NOT NULL,
        limite_superior  NUMERIC(12,4) NOT NULL,
        cpk_objetivo     NUMERIC(5,2)  NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS flujos (
        id_flujo         VARCHAR(12) PRIMARY KEY,
        iniciado_en      TIMESTAMP   NOT NULL,
        cerrado_en       TIMESTAMP   NOT NULL,
        linea            VARCHAR(40) NOT NULL,
        turno            VARCHAR(4)  NOT NULL,
        operador         VARCHAR(40) NOT NULL,
        lote             VARCHAR(12) NOT NULL,
        piezas_ok        INTEGER     NOT NULL,
        piezas_nok       INTEGER     NOT NULL,
        cotas_nok        INTEGER     NOT NULL,
        causa_principal  VARCHAR(24) NOT NULL,
        estado           VARCHAR(4)  NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS piezas (
        id_flujo               VARCHAR(12) NOT NULL,
        codigo_pieza           VARCHAR(8)  NOT NULL,
        serie_pieza            VARCHAR(24) NOT NULL,
        estacion               VARCHAR(40) NOT NULL,
        fabricado_en           TIMESTAMP   NOT NULL,
        temperatura_c          NUMERIC(6,2),
        id_herramienta         VARCHAR(24) NOT NULL,
        piezas_en_herramienta  INTEGER     NOT NULL,
        n_cotas_nok            INTEGER     NOT NULL,
        cotas_nok              VARCHAR(400),
        causa_defecto          VARCHAR(24) NOT NULL,
        estado                 VARCHAR(4)  NOT NULL,
        PRIMARY KEY (id_flujo, codigo_pieza)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mediciones (
        id_flujo     VARCHAR(12) NOT NULL,
        codigo_pieza VARCHAR(8)  NOT NULL,
        codigo_cota  VARCHAR(12) NOT NULL,
        valor        NUMERIC(12,4) NOT NULL,
        desviacion   NUMERIC(12,4) NOT NULL,
        ok           BOOLEAN     NOT NULL,
        PRIMARY KEY (id_flujo, codigo_pieza, codigo_cota)
    )
    """,
]


class Almacen:
    """Interfaz común; las subclases cambian solo el conector."""

    marcador = "?"
    nombre = "base"

    def __init__(self) -> None:
        self._conexion: Any = None
        self._en_transaccion = False

    # -- transacciones -----------------------------------------------------
    @contextmanager
    def transaccion(self):
        """Agrupa varias sentencias en un solo commit.

        Contra una base remota (Supabase) cada commit cuesta un viaje de red
        completo, así que insertar 82 mediciones en una sola transacción es
        mucho más rápido que confirmarlas una por una.
        """
        self._en_transaccion = True
        try:
            yield
        except Exception:
            try:
                self._conexion.rollback()
            finally:
                self._en_transaccion = False
            raise
        else:
            self._en_transaccion = False
            self._conexion.commit()

    def _confirmar(self) -> None:
        if not self._en_transaccion and self._conexion is not None:
            self._conexion.commit()

    # -- ciclo de vida -----------------------------------------------------
    def conectar(self) -> None:  # pragma: no cover - lo define la subclase
        raise NotImplementedError

    def cerrar(self) -> None:
        if self._conexion is not None:
            try:
                self._conexion.close()
            finally:
                self._conexion = None

    # -- SQL ---------------------------------------------------------------
    def _ejecutar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        cursor = self._conexion.cursor()
        cursor.execute(sql, tuple(params))
        return cursor

    def ejecutar(self, sql: str, params: Sequence[Any] = ()) -> None:
        cursor = self._ejecutar(sql, params)
        cursor.close()
        self._confirmar()

    def ejecutarmany(self, sql: str, filas: Iterable[Sequence[Any]]) -> None:
        filas = list(filas)
        if not filas:
            return
        cursor = self._conexion.cursor()
        cursor.executemany(sql, [tuple(f) for f in filas])
        cursor.close()
        self._confirmar()

    # -- adaptación de valores --------------------------------------------
    def adaptar(self, valor: Any) -> Any:
        return valor

    # -- operaciones de negocio -------------------------------------------
    def crear_esquema(self, config: Config) -> None:
        """Crea las tablas solo si faltan y mantiene el catálogo sincronizado.

        El DDL contra Supabase es lento (varios segundos por sentencia), así que
        se evita en cada arranque: se comprueba primero si el esquema ya existe.
        """
        if not self._esquema_existe():
            with self.transaccion():
                for sentencia in DDL:
                    self.ejecutar(sentencia)
        with self.transaccion():
            self._sembrar_catalogo(config)

    def _esquema_existe(self) -> bool:
        try:
            cursor = self._ejecutar("SELECT COUNT(*) FROM flujos")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception:
            try:
                self._conexion.rollback()
            except Exception:
                pass
            return False

    def _insertar_muchos(
        self,
        tabla: str,
        columnas: Sequence[str],
        filas: Sequence[Sequence[Any]],
        conflicto: str = "ON CONFLICT DO NOTHING",
    ) -> None:
        """INSERT multi-fila en una sola sentencia.

        Contra una base remota, 82 INSERT separados son 82 viajes de red
        (~15 s); una sola sentencia los resuelve en un viaje.
        """
        filas = [tuple(f) for f in filas]
        if not filas:
            return
        p = self.marcador
        tupla = "(" + ", ".join([p] * len(columnas)) + ")"
        valores = ", ".join([tupla] * len(filas))
        parametros = [valor for fila in filas for valor in fila]
        self.ejecutar(
            f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES {valores} {conflicto}",
            parametros,
        )

    def _sembrar_catalogo(self, config: Config) -> None:
        self._insertar_muchos(
            "dim_piezas",
            ["id_pieza", "codigo_pieza", "nombre_pieza"],
            [(c.id, c.codigo, c.nombre) for c in config.componentes],
            "ON CONFLICT (id_pieza) DO UPDATE SET"
            " codigo_pieza = EXCLUDED.codigo_pieza,"
            " nombre_pieza = EXCLUDED.nombre_pieza",
        )

        self._insertar_muchos(
            "dim_cotas",
            [
                "codigo_cota",
                "id_pieza",
                "codigo_pieza",
                "nombre_cota",
                "tipo",
                "unidad",
                "nominal",
                "limite_inferior",
                "limite_superior",
                "cpk_objetivo",
            ],
            [
                (
                    cota.codigo,
                    componente.id,
                    componente.codigo,
                    cota.nombre,
                    cota.tipo,
                    cota.unidad,
                    cota.nominal,
                    cota.limite_inferior,
                    cota.limite_superior,
                    cota.cpk_objetivo,
                )
                for componente in config.componentes
                for cota in componente.cotas
            ],
            "ON CONFLICT (codigo_cota) DO UPDATE SET"
            " id_pieza = EXCLUDED.id_pieza,"
            " codigo_pieza = EXCLUDED.codigo_pieza,"
            " nombre_cota = EXCLUDED.nombre_cota,"
            " tipo = EXCLUDED.tipo,"
            " unidad = EXCLUDED.unidad,"
            " nominal = EXCLUDED.nominal,"
            " limite_inferior = EXCLUDED.limite_inferior,"
            " limite_superior = EXCLUDED.limite_superior,"
            " cpk_objetivo = EXCLUDED.cpk_objetivo",
        )

    def _insertar_devolviendo(
        self,
        tabla: str,
        columnas: Sequence[str],
        filas: Sequence[Sequence[Any]],
        devolver: str,
        conflicto: str = "",
    ) -> list[tuple]:
        """INSERT multi-fila con RETURNING (para recuperar los id generados)."""
        filas = [tuple(f) for f in filas]
        if not filas:
            return []
        p = self.marcador
        tupla = "(" + ", ".join([p] * len(columnas)) + ")"
        valores = ", ".join([tupla] * len(filas))
        parametros = [valor for fila in filas for valor in fila]
        cursor = self._ejecutar(
            f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES {valores}"
            f" {conflicto} RETURNING {devolver}",
            parametros,
        )
        resultado = cursor.fetchall()
        cursor.close()
        self._confirmar()
        return list(resultado)

    # -- consultas de continuación ----------------------------------------
    def ultimo_flujo(self) -> int:
        """Número del último flujo guardado (0 si la base está vacía)."""
        cursor = self._ejecutar("SELECT MAX(id_flujo) FROM flujos")
        valor = cursor.fetchone()[0]
        cursor.close()
        if not valor:
            return 0
        try:
            return int(str(valor).split("-")[-1])
        except (TypeError, ValueError):
            return 0

    def contadores_piezas(self) -> dict[str, int]:
        """Cuántas unidades de cada componente se han fabricado ya."""
        cursor = self._ejecutar(
            "SELECT codigo_pieza, COUNT(*) FROM piezas GROUP BY codigo_pieza"
        )
        filas = cursor.fetchall()
        cursor.close()
        return {str(codigo): int(total) for codigo, total in filas}

    def ultimo_cierre(self) -> datetime | None:
        """Momento en que terminó el último flujo, para continuar el reloj."""
        cursor = self._ejecutar("SELECT MAX(cerrado_en) FROM flujos")
        valor = cursor.fetchone()[0]
        cursor.close()
        if valor is None:
            return None
        if isinstance(valor, datetime):
            return valor
        return datetime.fromisoformat(str(valor))

    def conteos(self) -> dict[str, int]:
        """Cuántas filas hay en cada tabla."""
        resultado: dict[str, int] = {}
        for tabla in ("dim_piezas", "dim_cotas", "flujos", "piezas", "mediciones"):
            cursor = self._ejecutar(f"SELECT COUNT(*) FROM {tabla}")
            resultado[tabla] = int(cursor.fetchone()[0])
            cursor.close()
        return resultado

    def resumen_estado(self) -> dict[str, Any]:
        """Totales de producción para el comando --estado."""
        datos: dict[str, Any] = {}
        cursor = self._ejecutar(
            "SELECT COUNT(*), COALESCE(SUM(piezas_ok), 0), COALESCE(SUM(piezas_nok), 0)"
            " FROM flujos"
        )
        datos["flujos"], datos["piezas_ok"], datos["piezas_nok"] = cursor.fetchone()
        cursor.close()

        cursor = self._ejecutar("SELECT COUNT(*) FROM piezas")
        datos["piezas"] = int(cursor.fetchone()[0])
        cursor.close()

        cursor = self._ejecutar("SELECT COUNT(*) FROM mediciones")
        datos["mediciones"] = int(cursor.fetchone()[0])
        cursor.close()

        cursor = self._ejecutar(
            "SELECT causa_defecto, COUNT(*) FROM piezas WHERE estado = 'NOK'"
            " GROUP BY causa_defecto ORDER BY COUNT(*) DESC"
        )
        datos["causas"] = [(str(c), int(n)) for c, n in cursor.fetchall()]
        cursor.close()

        cursor = self._ejecutar(
            "SELECT codigo_cota, COUNT(*) FROM mediciones WHERE ok = FALSE"
            " GROUP BY codigo_cota ORDER BY COUNT(*) DESC LIMIT 5"
        )
        datos["cotas_criticas"] = [(str(c), int(n)) for c, n in cursor.fetchall()]
        cursor.close()

        datos["ultimo_flujo"] = self.ultimo_flujo()
        datos["ultimo_cierre"] = self.ultimo_cierre()
        return datos

    def guardar_flujo(self, flujo: dict[str, Any], piezas: Sequence[dict[str, Any]],
                      mediciones: Sequence[dict[str, Any]],
                      config: Config | None = None) -> None:
        with self.transaccion():
            self._insertar_muchos(
                "flujos",
                [
                    "id_flujo", "iniciado_en", "cerrado_en", "linea", "turno",
                    "operador", "lote", "piezas_ok", "piezas_nok", "cotas_nok",
                    "causa_principal", "estado",
                ],
                [
                    (
                        flujo["id_flujo"],
                        self.adaptar(flujo["iniciado_en"]),
                        self.adaptar(flujo["cerrado_en"]),
                        flujo["linea"],
                        flujo["turno"],
                        flujo["operador"],
                        flujo["lote"],
                        flujo["piezas_ok"],
                        flujo["piezas_nok"],
                        flujo["cotas_nok"],
                        flujo["causa_principal"],
                        flujo["estado"],
                    )
                ],
            )

            self._insertar_muchos(
                "piezas",
                [
                    "id_flujo", "codigo_pieza", "serie_pieza", "estacion",
                    "fabricado_en", "temperatura_c", "id_herramienta",
                    "piezas_en_herramienta", "n_cotas_nok", "cotas_nok",
                    "causa_defecto", "estado",
                ],
                [
                    (
                        pieza["id_flujo"],
                        pieza["codigo_pieza"],
                        pieza["serie_pieza"],
                        pieza["estacion"],
                        self.adaptar(pieza["fabricado_en"]),
                        pieza["temperatura_c"],
                        pieza["id_herramienta"],
                        pieza["piezas_en_herramienta"],
                        pieza["n_cotas_nok"],
                        pieza["cotas_nok"],
                        pieza["causa_defecto"],
                        pieza["estado"],
                    )
                    for pieza in piezas
                ],
            )

            self._insertar_muchos(
                "mediciones",
                [
                    "id_flujo", "codigo_pieza", "codigo_cota", "valor",
                    "desviacion", "ok",
                ],
                [
                    (
                        m["id_flujo"],
                        m["codigo_pieza"],
                        m["codigo_cota"],
                        m["valor"],
                        m["desviacion"],
                        m["ok"],
                    )
                    for m in mediciones
                ],
            )


class AlmacenSQLite(Almacen):
    nombre = "sqlite"

    def __init__(self, ruta: str | Path) -> None:
        super().__init__()
        self.ruta = Path(ruta)

    def conectar(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._conexion = sqlite3.connect(self.ruta)

    def adaptar(self, valor: Any) -> Any:
        # Desde Python 3.12 sqlite3 ya no adapta datetime automáticamente.
        if isinstance(valor, datetime):
            return valor.strftime("%Y-%m-%d %H:%M:%S")
        return valor


class AlmacenPostgres(Almacen):
    nombre = "postgres"
    marcador = "%s"

    def __init__(self, parametros: BaseDatos, password: str, timeout: int = 15) -> None:
        super().__init__()
        self.parametros = parametros
        self.mapeo = parametros.mapeo_piezas
        self.esquema = parametros.esquema
        self._password = password
        self._timeout = timeout

    def conectar(self) -> None:
        try:
            import pg8000.dbapi  # type: ignore
        except ImportError as error:  # pragma: no cover
            raise RuntimeError(
                "Falta el conector de Postgres. Instala con: pip install pg8000"
            ) from error

        import ssl

        contexto = ssl.create_default_context()
        contexto.check_hostname = False
        contexto.verify_mode = ssl.CERT_NONE

        self._conexion = pg8000.dbapi.connect(
            host=self.parametros.host,
            port=int(self.parametros.puerto),
            database=self.parametros.base,
            user=self.parametros.usuario,
            password=self._password,
            timeout=self._timeout,
            ssl_context=contexto,
        )


def crear_almacen(datos: BaseDatos, password: str | None) -> Almacen:
    """Fábrica: devuelve el almacén configurado y ya conectado."""
    if datos.motor == "sqlite":
        almacen: Almacen = AlmacenSQLite(datos.archivo_sqlite)
        almacen.conectar()
        return almacen

    if datos.motor == "postgres":
        if not password:
            raise RuntimeError(
                "Falta la contraseña de la base. Defínela en config/.env como "
                f"{VARIABLE_PASSWORD}=tu_contraseña"
            )
        if datos.estructura == "calidad":
            from .almacen_calidad import AlmacenCalidad

            almacen = AlmacenCalidad(datos, password)
        else:
            almacen = AlmacenPostgres(datos, password)
        almacen.conectar()
        return almacen

    raise ValueError(f"Motor de base de datos desconocido: {datos.motor!r}")
