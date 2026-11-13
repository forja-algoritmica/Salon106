"""Exportación de resultados a archivos listos para Power BI."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from .config import Config
from .generador import Resultado


def _celda(valor: Any) -> str:
    """Convierte un valor a texto estable (sin notación científica ni ruido)."""
    if isinstance(valor, float):
        return repr(round(valor, 6))
    return str(valor)


def _escribir(
    ruta: Path,
    filas: Sequence[dict[str, Any]],
    columnas: Iterable[str],
    separador: str,
) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    nombres = list(columnas)
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(
            archivo,
            fieldnames=nombres,
            delimiter=separador,
            extrasaction="ignore",
            restval="",
        )
        escritor.writeheader()
        for fila in filas:
            escritor.writerow({k: _celda(fila.get(k, "")) for k in nombres})


def guardar_resultado(
    resultado: Resultado, config: Config, carpeta: str | Path | None = None
) -> dict[str, Path]:
    """Guarda todas las tablas y devuelve las rutas generadas."""
    destino = Path(carpeta or config.salida.carpeta)
    destino.mkdir(parents=True, exist_ok=True)
    separador = config.salida.separador
    rutas: dict[str, Path] = {}

    columnas_piezas = [
        "id_conjunto",
        "marca_tiempo",
        "fecha",
        "turno",
        "operador",
        "lote",
        "linea",
        "estacion",
        "id_pieza",
        "codigo_pieza",
        "nombre_pieza",
        "serie_pieza",
        "id_herramienta",
        "piezas_en_herramienta",
        "temperatura_c",
        "n_cotas_nok",
        "cotas_nok",
        "estado",
        "causa_defecto",
        "etiqueta",
    ]
    rutas["piezas"] = destino / "piezas.csv"
    _escribir(rutas["piezas"], resultado.piezas, columnas_piezas, separador)

    columnas_conjuntos = [
        "id_conjunto",
        "marca_tiempo",
        "fecha",
        "turno",
        "operador",
        "lote",
        "linea",
        "piezas_ok",
        "piezas_nok",
        "cotas_nok",
        "causa_principal",
        "estado",
        "etiqueta",
    ]
    rutas["conjuntos"] = destino / "conjuntos.csv"
    _escribir(rutas["conjuntos"], resultado.conjuntos, columnas_conjuntos, separador)

    if resultado.mediciones:
        columnas_mediciones = [
            "id_conjunto",
            "id_pieza",
            "codigo_pieza",
            "serie_pieza",
            "codigo_cota",
            "nombre_cota",
            "tipo",
            "unidad",
            "nominal",
            "limite_inferior",
            "limite_superior",
            "valor",
            "desviacion",
            "ok",
        ]
        rutas["mediciones"] = destino / "mediciones.csv"
        _escribir(
            rutas["mediciones"], resultado.mediciones, columnas_mediciones, separador
        )

    # Tablas de dimensión (se reescriben en cada corrida desde el catálogo).
    filas_piezas_dim = [
        {"id_pieza": c.id, "codigo_pieza": c.codigo, "nombre_pieza": c.nombre, "cotas": len(c.cotas)}
        for c in config.componentes
    ]
    rutas["dim_piezas"] = destino / "dim_piezas.csv"
    _escribir(
        rutas["dim_piezas"],
        filas_piezas_dim,
        ["id_pieza", "codigo_pieza", "nombre_pieza", "cotas"],
        separador,
    )

    filas_cotas_dim = [
        {
            "codigo_cota": cota.codigo,
            "id_pieza": componente.id,
            "codigo_pieza": componente.codigo,
            "nombre_cota": cota.nombre,
            "tipo": cota.tipo,
            "unidad": cota.unidad,
            "nominal": cota.nominal,
            "tol_inf": cota.tol_inf,
            "tol_sup": cota.tol_sup,
            "limite_inferior": round(cota.limite_inferior, 6),
            "limite_superior": round(cota.limite_superior, 6),
            "cpk_objetivo": cota.cpk_objetivo,
        }
        for componente in config.componentes
        for cota in componente.cotas
    ]
    rutas["dim_cotas"] = destino / "dim_cotas.csv"
    _escribir(
        rutas["dim_cotas"],
        filas_cotas_dim,
        [
            "codigo_cota",
            "id_pieza",
            "codigo_pieza",
            "nombre_cota",
            "tipo",
            "unidad",
            "nominal",
            "tol_inf",
            "tol_sup",
            "limite_inferior",
            "limite_superior",
            "cpk_objetivo",
        ],
        separador,
    )

    rutas["resumen_piezas"] = destino / "resumen_piezas.csv"
    _escribir(
        rutas["resumen_piezas"],
        resultado.resumen["por_pieza"],
        ["codigo_pieza", "nombre_pieza", "cotas", "piezas", "nok", "tasa_nok", "cpk_min"],
        separador,
    )

    rutas["resumen_cotas"] = destino / "resumen_cotas.csv"
    _escribir(
        rutas["resumen_cotas"],
        sorted(resultado.resumen["por_cota"], key=lambda f: -f["tasa_nok"]),
        [
            "codigo_cota",
            "codigo_pieza",
            "nombre",
            "tipo",
            "unidad",
            "nominal",
            "limite_inferior",
            "limite_superior",
            "media",
            "sigma",
            "cp",
            "cpk",
            "nok",
            "tasa_nok",
        ],
        separador,
    )

    rutas["resumen"] = destino / "resumen.json"
    rutas["resumen"].write_text(
        json.dumps(resultado.resumen, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if config.salida.incluir_parquet:
        rutas.update(_guardar_parquet(resultado, destino))

    return rutas


def _guardar_parquet(resultado: Resultado, destino: Path) -> dict[str, Path]:
    # Import dinámico: así PyInstaller no arrastra pandas/scipy/matplotlib al
    # ejecutable (lo harían pesar ~100 MB de más). Parquet queda disponible
    # solo cuando se corre desde Python con pandas instalado.
    try:
        pandas = importlib.import_module("pandas")
    except ImportError as error:  # pragma: no cover - depende del entorno
        raise RuntimeError(
            "Para exportar Parquet instala 'pandas' y 'pyarrow': "
            "pip install pandas pyarrow"
        ) from error

    rutas: dict[str, Path] = {}
    for nombre, filas in (
        ("piezas", resultado.piezas),
        ("mediciones", resultado.mediciones),
        ("conjuntos", resultado.conjuntos),
    ):
        if not filas:
            continue
        ruta = destino / f"{nombre}.parquet"
        pandas.DataFrame(filas).to_parquet(ruta, index=False)
        rutas[f"{nombre}_parquet"] = ruta
    return rutas
