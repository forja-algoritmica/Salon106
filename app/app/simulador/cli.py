"""Interfaz de línea de comandos del generador de datos."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import cargar_config, config_por_defecto, guardar_config
from .exportacion import guardar_resultado
from .generador import calibrar_escala, generar

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_CONFIG = RAIZ / "config"


def _configurar_consola() -> None:
    """Evita que los acentos se vean como '?' en la consola de Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover - consola redirigida o sin permisos
        pass


def _construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generar_datos",
        description=(
            "Genera el histórico del ensamble del brazo de retroexcavadora: "
            "piezas, medidas por cota y resultado del ensamble."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config", default=str(CARPETA_CONFIG), help="Carpeta con el catálogo y proceso.json"
    )
    parser.add_argument("--conjuntos", type=int, default=None, help="Ensamble completos a generar")
    parser.add_argument("--semilla", type=int, default=None, help="Semilla aleatoria")
    parser.add_argument(
        "--escala-defectos",
        type=float,
        default=None,
        help="Multiplicador de las causas especiales de defecto (1.0 = la configurada)",
    )
    parser.add_argument(
        "--tasa-objetivo",
        type=float,
        default=None,
        help="Ajusta la escala para lograr esta tasa de piezas NOK (ej. 0.03)",
    )
    parser.add_argument(
        "--tasa-conjuntos",
        type=float,
        default=None,
        help="Ajusta la escala para lograr esta tasa de ensambles NOK (ej. 0.02)",
    )
    parser.add_argument("--salida", default=None, help="Carpeta donde escribir los archivos")
    parser.add_argument("--separador", default=None, help="Separador de columnas del CSV")
    parser.add_argument("--sin-mediciones", action="store_true", help="No generar la tabla de mediciones")
    parser.add_argument("--parquet", action="store_true", help="Exportar además en Parquet")
    parser.add_argument(
        "--crear-config",
        metavar="CARPETA",
        nargs="?",
        const=str(CARPETA_CONFIG),
        help="Escribe el catálogo y proceso.json por defecto y termina",
    )
    parser.add_argument(
        "--guardar-config",
        action="store_true",
        help="Guarda en disco los cambios hechos por consola",
    )
    return parser


def _imprimir_resumen(resumen: dict) -> None:
    print()
    print("  RESUMEN DE LA CORRIDA")
    print("  " + "-" * 62)
    print(f"  Conjuntos generados   : {resumen['conjuntos']:>8,}".replace(",", "."))
    print(
        f"  Piezas fabricadas     : {resumen['piezas_fabricadas']:>8,}".replace(",", ".")
        + f"   ({resumen['componentes_por_conjunto']} por conjunto)"
    )
    print(f"  Mediciones por conjunto: {resumen['cotas_por_conjunto']:>7}")
    print()
    print(f"  Piezas NOK            : {resumen['piezas_nok']:>8,}".replace(",", "."))
    print(f"  Tasa NOK de piezas    : {resumen['tasa_nok'] * 100:>8.2f} %")
    print(f"  Conjuntos NOK         : {resumen['conjuntos_nok']:>8,}".replace(",", "."))
    print(f"  Tasa NOK de conjuntos : {resumen['tasa_conjuntos_nok'] * 100:>8.2f} %")
    print()

    if resumen["por_causa"]:
        print("  Causas de no conformidad de piezas")
        for causa, cantidad in resumen["por_causa"].items():
            print(
                f"    {causa:<22}{cantidad:>8}"
                f"  ({cantidad / resumen['piezas_fabricadas'] * 100:5.2f} %)"
            )
        print()

    print("  Resultado por componente")
    print(f"    {'pieza':<8}{'nombre':<16}{'cotas':>7}{'NOK':>8}{'tasa':>9}{'Cpk min':>9}")
    for fila in resumen["por_pieza"]:
        print(
            f"    {fila['codigo_pieza']:<8}{fila['nombre_pieza'][:15]:<16}"
            f"{fila['cotas']:>7}{fila['nok']:>8}"
            f"{fila['tasa_nok'] * 100:>8.2f} %{fila['cpk_min']:>9.2f}"
        )
    print()

    print("  Cotas más problemáticas")
    print(f"    {'cota':<10}{'componente':<12}{'tasa':>8}{'Cpk':>8}   nombre")
    for fila in resumen["peores_cotas"][:8]:
        print(
            f"    {fila['codigo_cota']:<10}{fila['codigo_pieza']:<12}"
            f"{fila['tasa_nok'] * 100:>7.2f} %{fila['cpk']:>8.2f}   "
            f"{fila['nombre'][:34]}"
        )
    print()


def main(argv: list[str] | None = None) -> int:
    _configurar_consola()
    parser = _construir_parser()
    args = parser.parse_args(argv)

    carpeta_config = Path(args.config)

    # 1) Modo "crear configuración".
    if args.crear_config:
        destino = Path(args.crear_config)
        rutas = guardar_config(config_por_defecto(), destino)
        print(f"Catálogo creado en:  {rutas['catalogo']}")
        print(f"Parámetros en:       {rutas['proceso']}")
        return 0

    # 2) Cargar configuración (si no existe, se crea la de por defecto).
    if not (carpeta_config / "catalogo_cotas.csv").exists():
        if carpeta_config == CARPETA_CONFIG:
            guardar_config(config_por_defecto(), carpeta_config)
            print(f"Configuración inicial creada en: {carpeta_config}")
        else:
            print(
                f"Error: no se encontró el catálogo en {carpeta_config}", file=sys.stderr
            )
            return 2

    try:
        config = cargar_config(carpeta_config)
    except (ValueError, TypeError, FileNotFoundError) as error:
        print(f"Error en la configuración: {error}", file=sys.stderr)
        return 2

    # 3) Sobrescrituras desde la línea de comandos.
    if args.conjuntos is not None:
        config.proceso.conjuntos = args.conjuntos
    if args.semilla is not None:
        config.proceso.semilla = args.semilla
    if args.escala_defectos is not None:
        config.defectos.escala = args.escala_defectos
    if args.salida is not None:
        config.salida.carpeta = args.salida
    if args.separador is not None:
        config.salida.separador = args.separador
    if args.sin_mediciones:
        config.salida.incluir_mediciones = False
    if args.parquet:
        config.salida.incluir_parquet = True

    try:
        config.validar()
    except (ValueError, TypeError) as error:
        print(f"Error en la configuración: {error}", file=sys.stderr)
        return 2

    print(
        f"Catálogo: {len(config.componentes)} componentes, "
        f"{len(config.cotas)} cotas dimensionales."
    )

    # 4) Calibración opcional a una tasa de defecto objetivo.
    objetivo = args.tasa_objetivo
    nivel = "piezas"
    if args.tasa_conjuntos is not None:
        if objetivo is not None:
            print(
                "Error: use --tasa-objetivo o --tasa-conjuntos, no ambas.",
                file=sys.stderr,
            )
            return 2
        objetivo = args.tasa_conjuntos
        nivel = "conjuntos"

    if objetivo is not None:
        if not 0.0 <= objetivo <= 1.0:
            print(
                "Error: la tasa objetivo debe estar entre 0 y 1", file=sys.stderr
            )
            return 2
        etiqueta = "piezas" if nivel == "piezas" else "ensambles"
        print(f"Calibrando para una tasa de {objetivo * 100:.2f} % de {etiqueta} NOK ...")
        config.defectos.escala = calibrar_escala(
            config,
            tasa_objetivo=objetivo,
            conjuntos=config.proceso.conjuntos,
            semilla=config.proceso.semilla,
            nivel=nivel,
        )
        print(f"Escala calibrada: {config.defectos.escala}")

    # 5) Generar y guardar.
    resultado = generar(config)
    rutas = guardar_resultado(resultado, config)

    if args.guardar_config:
        guardar_config(config, carpeta_config)

    if objetivo is not None:
        clave = "tasa_nok" if nivel == "piezas" else "tasa_conjuntos_nok"
        lograda = resultado.resumen[clave]
        if abs(lograda - objetivo) > 0.01:
            print(
                f"  Aviso: no se alcanzó el {objetivo * 100:.2f} % "
                f"(se obtuvo {lograda * 100:.2f} %). La deriva y la variación natural "
                "ponen un piso que la escala no puede bajar.",
                file=sys.stderr,
            )

    _imprimir_resumen(resultado.resumen)
    print("  Archivos generados")
    for nombre, ruta in rutas.items():
        print(f"    {nombre:<16} {ruta}")
    print()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
