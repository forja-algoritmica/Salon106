"""Punto de entrada: corre la línea de ensamble de forma continua.

Cada flujo fabrica un ensamble completo (una pieza de cada componente, medida
estación por estación) y lo guarda en la base de datos. Al cerrar el flujo, la
línea arranca el siguiente con los mismos procesos.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, time as hora, timedelta
from pathlib import Path

from . import consola
from .almacen import BaseDatos, crear_almacen, leer_env, resolver_password
from .config import cargar_config, config_por_defecto, guardar_config
from .generador import calibrar_escala, generar
from .linea import Linea
from .rutas import carpeta_base, resolver

CARPETA_CONFIG = "config"

# Traducción por defecto de los códigos internos a los del cliente.
MAPEO_POR_DEFECTO = {
    "BAS": "BASE-001",
    "BR1": "BRZ-001",
    "CIL": "CIL-001",
    "CCH": "CCH-001",
    "EST": "EST-001",
    "PLM": "PLM-001",
    "TNS": "TNS-001",
}


def _construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="linea_ensamble",
        description=(
            "Simula la línea de ensamble del brazo de retroexcavadora. "
            "Cada flujo produce un ensamble completo y se guarda en la base de datos."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--config", default=CARPETA_CONFIG, help="Carpeta de configuración")
    parser.add_argument(
        "--flujos", type=int, default=0, help="Cuántos ensambles generar (0 = continuo)"
    )
    parser.add_argument("--semilla", type=int, default=None, help="Semilla aleatoria")
    parser.add_argument(
        "--escala-defectos",
        type=float,
        default=None,
        help="Multiplicador de las causas especiales de defecto",
    )
    parser.add_argument(
        "--deriva",
        type=float,
        default=None,
        metavar="SIGMAS",
        help="Deriva acumulada por desgaste al final de la vida de la herramienta",
    )
    parser.add_argument(
        "--tasa-defectos",
        type=float,
        default=None,
        metavar="P",
        help="Tasa objetivo de PIEZAS NOK, ej. 0.03 = 3%% (se calibra al arrancar)",
    )
    parser.add_argument(
        "--tasa-ensambles",
        type=float,
        default=None,
        metavar="P",
        help="Tasa objetivo de ENSAMBLES NOK, ej. 0.02 = 2%% (se calibra al arrancar)",
    )
    parser.add_argument(
        "--pausa", type=float, default=0.0, help="Segundos de espera entre flujos (solo visual)"
    )
    parser.add_argument("--detallado", action="store_true", help="Mostrar todas las cotas")
    parser.add_argument(
        "--reloj",
        choices=["simulado", "real"],
        default=None,
        help=(
            "simulado: avanza 30 min por ensamble (por defecto); "
            "real: marca cada pieza con la hora del equipo"
        ),
    )
    parser.add_argument(
        "--desde",
        metavar="AAAA-MM-DD",
        default=None,
        help="Fecha inicial del histórico (reparte los ensambles desde ese día)",
    )
    parser.add_argument(
        "--hasta",
        metavar="AAAA-MM-DD",
        default=None,
        help="Fecha final del histórico (se usa junto con --desde)",
    )
    parser.add_argument(
        "--dias",
        type=int,
        metavar="N",
        default=None,
        help="Genera el histórico de los últimos N días, hasta hoy",
    )
    parser.add_argument("--sin-db", action="store_true", help="No escribir en la base de datos")
    parser.add_argument(
        "--db",
        choices=["postgres", "sqlite"],
        default=None,
        help="Forzar el motor de base de datos",
    )
    parser.add_argument(
        "--cada", type=int, default=10, help="Cada cuántos flujos mostrar el acumulado"
    )
    parser.add_argument(
        "--crear-config", action="store_true", help="Escribe la configuración por defecto y termina"
    )
    parser.add_argument(
        "--lote",
        type=int,
        default=None,
        metavar="N",
        help="En vez de correr la línea, genera N ensambles en archivos CSV",
    )
    parser.add_argument(
        "--estado",
        action="store_true",
        help="Muestra el estado de la base de datos y termina",
    )
    parser.add_argument(
        "--limpiar-catalogos",
        action="store_true",
        help="Borra cotas del catálogo en la base que no están en el CSV y no tienen mediciones",
    )
    parser.add_argument(
        "--reiniciar",
        action="store_true",
        help="Vacía revisiones y mediciones (conserva el catálogo de piezas y cotas)",
    )
    parser.add_argument(
        "--si",
        action="store_true",
        help="No pide confirmación para --reiniciar",
    )
    return parser


def _cargar_entorno(carpeta_config: Path) -> None:
    """Carga el .env del repositorio si no hay variables DB_* en el entorno.

    Así `python app\\generador_datos.py` funciona desde una consola limpia
    (o desde un .bat) sin tener que exportar las variables a mano.
    """
    if os.environ.get("DB_HOST"):
        return
    candidatas = [
        carpeta_config / ".env",
        carpeta_config.parent / ".env",
        carpeta_config.parent.parent / ".env",
    ]
    for ruta in candidatas:
        if not ruta.exists():
            continue
        for clave, valor in leer_env(ruta).items():
            os.environ.setdefault(clave, valor)
        if os.environ.get("DB_HOST"):
            return


def _cargar_base_datos(carpeta: Path, forzar: str | None) -> BaseDatos:
    """Lee la conexión del JSON y permite sobrescribirla con variables DB_*.

    En el contenedor (o en el repo) las credenciales llegan por `.env`, así que
    las variables de entorno tienen prioridad sobre el archivo.
    """
    ruta = carpeta / "base_datos.json"
    datos = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}

    host_env = os.environ.get("DB_HOST")
    base = BaseDatos(
        motor=datos.get("motor", "postgres" if host_env else "ninguno"),
        host=host_env or datos.get("host", ""),
        puerto=int(os.environ.get("DB_PORT") or datos.get("puerto", 5432)),
        base=os.environ.get("DB_NAME") or datos.get("base", "postgres"),
        usuario=os.environ.get("DB_USER") or datos.get("usuario", ""),
        sslmode=os.environ.get("DB_SSLMODE") or datos.get("sslmode", "require"),
        archivo_sqlite=datos.get("archivo_sqlite", "datos/linea.db"),
        estructura=datos.get("estructura", "calidad"),
        esquema=datos.get("esquema", "calidad_piezas"),
        mapeo_piezas=dict(datos.get("mapeo_piezas", MAPEO_POR_DEFECTO)),
    )
    if forzar:
        base.motor = forzar
    base.archivo_sqlite = str(resolver(base.archivo_sqlite))
    return base


def _preparar_config(carpeta: Path):
    if not (carpeta / "catalogo_cotas.csv").exists():
        guardar_config(config_por_defecto(), carpeta)
        consola.informacion(f"Configuración inicial creada en: {carpeta}")
    return cargar_config(carpeta)


def _calcular_rango(args) -> tuple[datetime, datetime] | None:
    """Interpreta --dias o --desde/--hasta y devuelve inicio y fin."""
    try:
        if args.dias is not None:
            if args.dias <= 0:
                consola.error("--dias debe ser mayor que 0.")
                return None
            fin = date.today()
            inicio = fin - timedelta(days=args.dias)
        else:
            if not args.desde or not args.hasta:
                consola.error("usa --desde y --hasta juntos, o solo --dias.")
                return None
            inicio = date.fromisoformat(args.desde)
            fin = date.fromisoformat(args.hasta)
    except ValueError:
        consola.error("Las fechas deben tener el formato AAAA-MM-DD (ej. 2026-10-14).")
        return None

    if fin <= inicio:
        consola.error("--hasta debe ser posterior a --desde.")
        return None

    # La jornada arranca a las 06:00, igual que los turnos del sistema.
    return datetime.combine(inicio, hora(6, 0)), datetime.combine(fin, hora(6, 0))


def _mostrar_estado(almacen, datos: BaseDatos) -> int:
    estado = almacen.resumen_estado()
    flujos = int(estado["flujos"] or 0)
    piezas = int(estado["piezas"] or 0)
    nok = int(estado["piezas_nok"] or 0)

    print()
    print(f"  {consola.NEGRITA}ESTADO DE LA BASE{consola.RESET}   {datos!r}")
    print("  " + "-" * 60)
    print(f"  Flujos registrados : {flujos}")
    print(f"  Piezas fabricadas  : {piezas}")
    print(f"  Mediciones         : {estado['mediciones']}")
    if estado.get("cotas_definidas"):
        print(f"  Cotas definidas    : {estado['cotas_definidas']}")
    print(f"  Piezas NOK         : {nok}")
    reparacion = int(estado.get("reparacion", 0) or 0)
    if reparacion:
        print(f"  Para reparación    : {reparacion}")
    if piezas:
        print(f"  Tasa NOK           : {consola.num(nok / piezas * 100, 2)} %")
    if estado["ultimo_flujo"]:
        print(f"  Último flujo       : FL-{estado['ultimo_flujo']:06d}")
    if estado["ultimo_cierre"]:
        print(f"  Último cierre      : {estado['ultimo_cierre']:%Y-%m-%d %H:%M}")

    if estado["causas"]:
        print()
        print("  Causas de defecto")
        for causa, cantidad in estado["causas"]:
            print(f"    {causa:<22}{cantidad:>8}")

    if estado["cotas_criticas"]:
        print()
        print("  Cotas con más rechazos")
        for cota, cantidad in estado["cotas_criticas"]:
            print(f"    {cota:<12}{cantidad:>8}")
    print()
    return 0


def main(argv: list[str] | None = None) -> int:
    consola.configurar_consola()
    parser = _construir_parser()
    args = parser.parse_args(argv)

    base = carpeta_base()
    carpeta_config = resolver(args.config)

    if args.crear_config:
        rutas = guardar_config(config_por_defecto(), carpeta_config)
        print(f"Catálogo:   {rutas['catalogo']}")
        print(f"Parámetros: {rutas['proceso']}")
        return 0

    try:
        config = _preparar_config(carpeta_config)
    except (ValueError, TypeError, FileNotFoundError) as error:
        consola.error(f"configuración inválida: {error}")
        return 2

    if args.semilla is not None:
        config.proceso.semilla = args.semilla
    if args.escala_defectos is not None:
        config.defectos.escala = args.escala_defectos
    if args.deriva is not None:
        config.defectos.deriva_total_sigmas = args.deriva
    if args.reloj is not None:
        config.proceso.reloj = args.reloj

    # --- Histórico repartido en un rango de fechas ------------------------
    rango_forzado = False
    if args.dias is not None or args.desde or args.hasta:
        if args.reloj == "real":
            consola.error("--desde/--hasta/--dias no se combinan con --reloj real.")
            return 2
        rango = _calcular_rango(args)
        if rango is None:
            return 2
        inicio, fin = rango
        cantidad = args.lote or args.flujos or config.proceso.conjuntos
        if cantidad <= 0:
            consola.error("Indica --flujos o --lote para saber cuántos ensambles repartir.")
            return 2
        segundos = (fin - inicio).total_seconds() / cantidad
        if segundos < 60:
            consola.error(
                f"Demasiados ensambles ({cantidad}) para ese rango: saldría uno cada "
                f"{segundos:.0f} s. Amplía el rango o reduce la cantidad."
            )
            return 2
        config.proceso.inicio = inicio.isoformat()
        config.proceso.reloj = "simulado"
        config.proceso.tiempo_ciclo_seg = segundos
        config.proceso.tiempo_ciclo_sigma = segundos * 0.05
        rango_forzado = True
        consola.informacion(
            f"Histórico: {cantidad} ensambles del {inicio:%d/%m/%Y} al {fin:%d/%m/%Y}"
            f" (uno cada {segundos / 60:.0f} min)."
        )

    # --- Tasa de defectos objetivo (calibración automática) ---------------
    if args.tasa_defectos is not None and args.tasa_ensambles is not None:
        consola.error("usa --tasa-defectos O --tasa-ensambles, no ambos.")
        return 2
    if args.escala_defectos is not None and (
        args.tasa_defectos is not None or args.tasa_ensambles is not None
    ):
        consola.error("usa --tasa-defectos O --escala-defectos, no ambos.")
        return 2

    objetivo = (
        args.tasa_defectos
        if args.tasa_defectos is not None
        else args.tasa_ensambles
    )
    if objetivo is not None:
        if not 0.0 <= objetivo <= 1.0:
            consola.error(
                "la tasa debe estar entre 0 y 1 (por ejemplo 0.03 para 3 %)."
            )
            return 2
        nivel = "piezas" if args.tasa_defectos is not None else "conjuntos"
        etiqueta = "piezas" if nivel == "piezas" else "ensambles"
        consola.informacion(
            f"Calibrando la línea a {consola.num(objetivo * 100, 2)} % de {etiqueta} NOK ..."
        )
        config.defectos.escala = calibrar_escala(
            config,
            tasa_objetivo=objetivo,
            conjuntos=max(config.proceso.conjuntos, 300),
            semilla=config.proceso.semilla,
            nivel=nivel,
        )
        consola.informacion(f"Escala de defectos calibrada: {config.defectos.escala}")
        referencia = generar(config, conjuntos=max(config.proceso.conjuntos, 300)).resumen
        consola.informacion(
            f"Referencia: {consola.num(referencia['tasa_nok'] * 100, 2)} % de piezas NOK "
            f"→ {consola.num(referencia['tasa_conjuntos_nok'] * 100, 2)} % de ensambles NOK"
        )

    # --- Modo lote: solo archivos CSV -----------------------------------
    if args.lote is not None:
        return _modo_lote(config, args.lote)

    # --- Base de datos ---------------------------------------------------
    _cargar_entorno(carpeta_config)
    datos = _cargar_base_datos(carpeta_config, args.db)
    if args.sin_db:
        datos.motor = "ninguno"

    almacen = None
    if datos.motor != "ninguno":
        password = resolver_password(carpeta_config)
        try:
            almacen = crear_almacen(datos, password)
        except Exception as error:  # conexión, credenciales, red
            texto = str(error)
            consola.error(texto)
            if "28P01" in texto or "password authentication failed" in texto:
                consola.informacion(
                    "La clave del rol y la del .env no coinciden. "
                    "Resincronízalas con:  python tools\\configurar_bd.py"
                )
            else:
                consola.informacion(
                    "Puedes correr sin base de datos con --sin-db, o revisar "
                    f"{carpeta_config / 'base_datos.json'} y el archivo .env"
                )
            return 2
        try:
            almacen.crear_esquema(config)
        except Exception as error:
            consola.error(f"no se pudo crear el esquema: {error}")
            almacen.cerrar()
            return 2

        if args.reiniciar:
            reiniciador = getattr(almacen, "reiniciar_hechos", None)
            if reiniciador is None:
                consola.aviso("Esta estructura no admite reinicio automático.")
            else:
                if not args.si:
                    respuesta = input(
                        "  Esto borra TODAS las revisiones y mediciones. "
                        "¿Continuar? (si/no): "
                    ).strip().lower()
                    if respuesta not in ("si", "sí", "s", "y", "yes"):
                        consola.informacion("Reinicio cancelado.")
                        almacen.cerrar()
                        return 0
                borrado = reiniciador()
                consola.informacion(
                    f"Borradas {borrado['revisiones']} revisiones y "
                    f"{borrado['mediciones']} mediciones."
                )

        if args.limpiar_catalogos:
            limpiador = getattr(almacen, "limpiar_catalogos", None)
            if limpiador is None:
                consola.aviso("Esta estructura no necesita limpieza de catálogo.")
            else:
                borradas = limpiador(config)
                consola.informacion(f"Cotas de catálogo eliminadas: {borradas}")

        if args.estado:
            codigo = _mostrar_estado(almacen, datos)
            almacen.cerrar()
            return codigo

        if args.reiniciar or args.limpiar_catalogos:
            almacen.cerrar()
            consola.informacion("Listo. Para arrancar la línea: Iniciar linea.bat")
            return 0

        destino = f"{datos!r}"
    else:
        if args.estado:
            consola.error("--estado necesita una base de datos configurada.")
            return 2
        destino = "sin base de datos (solo pantalla)"

    # --- Línea continua ---------------------------------------------------
    if almacen is not None and datos.estructura == "calidad":
        # El esquema del cliente guarda NUMERIC(10,2). Se redondea antes de
        # evaluar para que la terminal y el trigger den el mismo veredicto.
        for cota in config.cotas:
            cota.decimales = 2

    numero_inicial = 0
    contadores = None
    reloj_inicial = None
    if almacen is not None:
        try:
            numero_inicial = almacen.ultimo_flujo()
            contadores = almacen.contadores_piezas()
            reloj_inicial = almacen.ultimo_cierre()
        except Exception as error:
            consola.aviso(f"no se pudo leer el estado previo: {error}")
        if numero_inicial:
            consola.informacion(
                f"Retomando la línea en el flujo FL-{numero_inicial + 1:06d}."
            )
        if numero_inicial and rango_forzado:
            consola.aviso(
                "La base ya tiene "
                f"{numero_inicial} flujos: el histórico nuevo arrancará en la fecha "
                "indicada y quedará desordenado respecto a los datos anteriores. "
                "Para un histórico limpio usa --reiniciar antes."
            )

    linea = Linea(
        config,
        semilla=config.proceso.semilla,
        escala_defectos=config.defectos.escala,
        numero_inicial=numero_inicial,
        contadores=contadores,
        # Con un rango explícito se ignora el reloj guardado en la base.
        reloj_inicial=None if rango_forzado else reloj_inicial,
    )
    consola.cabecera(config, destino, args.flujos)
    cada = max(args.cada, 1)
    generados = 0

    try:
        while args.flujos == 0 or generados < args.flujos:
            flujo = linea.siguiente_flujo()
            generados += 1

            if almacen is not None:
                try:
                    almacen.guardar_flujo(
                        flujo.como_registro(),
                        flujo.piezas,
                        flujo.mediciones,
                        config=config,
                    )
                except Exception as error:
                    consola.error(f"no se pudo guardar {flujo.id_flujo}: {error}")
                    consola.informacion(
                        "La línea se detiene para no seguir generando datos que "
                        "no se están guardando."
                    )
                    return 2

            consola.flujo_terminado(
                flujo,
                config,
                detallado=args.detallado,
                tasa_acumulada=(
                    linea.total_nok / linea.total_piezas if linea.total_piezas else 0.0
                ),
            )
            if linea.numero % cada == 0:
                consola.acumulado(linea)

            if args.pausa:
                time.sleep(args.pausa)

    except KeyboardInterrupt:
        print()
        consola.informacion("Detenido por el usuario.")
    finally:
        if almacen is not None:
            almacen.cerrar()

    if linea.numero and linea.numero % cada != 0:
        consola.acumulado(linea)
    if linea.numero:
        print()
    return 0


def _modo_lote(config, cantidad: int) -> int:
    """Genera N ensambles en CSV (para entrenar el modelo o abrir en Power BI)."""
    from .exportacion import guardar_resultado
    from .generador import generar

    config.proceso.conjuntos = cantidad
    config.salida.carpeta = str(resolver(config.salida.carpeta))
    consola.informacion(f"Generando {cantidad} ensambles en lote ...")
    resultado = generar(config)
    rutas = guardar_resultado(resultado, config)

    resumen = resultado.resumen
    print()
    consola.informacion(
        f"{resumen['piezas_fabricadas']} piezas · {resumen['piezas_nok']} NOK "
        f"({consola.num(resumen['tasa_nok'] * 100, 2)} %) · "
        f"{resumen['conjuntos_nok']} ensambles NOK "
        f"({consola.num(resumen['tasa_conjuntos_nok'] * 100, 2)} %)"
    )
    for nombre, ruta in rutas.items():
        print(f"    {nombre:<16} {ruta}")
    print()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
