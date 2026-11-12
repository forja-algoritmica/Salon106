"""Salida por terminal de la línea de ensamble."""

from __future__ import annotations

import sys

from .config import Componente, Config
from .linea import Flujo, Linea


def _activar_ansi() -> bool:
    if not sys.stdout.isatty():
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            modo = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(modo)) == 0:
                return False
            return kernel32.SetConsoleMode(handle, modo.value | 0x0004) != 0
        except Exception:
            return False
    return True


def configurar_consola() -> None:
    """Fuerza UTF-8 en Windows para que acentos y bordes se vean bien."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover - consola redirigida
        pass


COLOR = _activar_ansi()
VERDE = "\033[92m" if COLOR else ""
ROJO = "\033[91m" if COLOR else ""
AMARILLO = "\033[93m" if COLOR else ""
GRIS = "\033[90m" if COLOR else ""
NEGRITA = "\033[1m" if COLOR else ""
RESET = "\033[0m" if COLOR else ""

ANCHO = 78


def num(valor: float, decimales: int = 3) -> str:
    """Número con separador de miles '.' y decimal ',' (formato español)."""
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _linea(caracter: str = "─") -> str:
    return caracter * ANCHO


def cabecera(config: Config, destino: str, flujos: int) -> None:
    print()
    print(NEGRITA + "  LÍNEA DE ENSAMBLE — BRAZO DE RETROEXCAVADORA" + RESET)
    print("  " + _linea())
    print(f"  Componentes : {len(config.componentes)}   Cotas por ensamble: {len(config.cotas)}")
    reloj = getattr(config.proceso, "reloj", "simulado")
    if reloj == "real":
        print("  Reloj       : hora real del equipo")
    else:
        print(
            f"  Reloj       : simulado ({config.proceso.tiempo_ciclo_seg / 60:.0f} min"
            " por ensamble, avanza más rápido que el calendario)"
        )
    print(f"  Destino     : {destino}")
    if flujos:
        print(f"  Flujos      : {flujos}")
    else:
        print("  Flujos      : continuo (Ctrl+C para detener)")
    print("  " + _linea())


def flujo_terminado(
    flujo: Flujo,
    config: Config,
    detallado: bool = False,
    tasa_acumulada: float | None = None,
) -> None:
    """Dibuja un ensamble completo, estación por estación."""
    cabecera_flujo = (
        f"{flujo.id_flujo}  {flujo.iniciado_en:%d/%m %H:%M}  "
        f"{flujo.turno}  {flujo.operador}  {flujo.lote}"
    )
    relleno = max(ANCHO - len(cabecera_flujo) - 2, 2)
    print()
    print(f"  {NEGRITA}{cabecera_flujo}{RESET} " + GRIS + "─" * relleno + RESET)

    medidas_por_cota = {m["codigo_cota"]: m for m in flujo.mediciones}
    total = len(flujo.piezas)

    for indice, pieza in enumerate(flujo.piezas, start=1):
        componente: Componente = config.componente(pieza["codigo_pieza"])
        ok = pieza["estado"] == "OK"
        buenas = len(componente.cotas) - pieza["n_cotas_nok"]
        marca = f"{VERDE}OK {RESET}" if ok else f"{ROJO}NOK{RESET}"

        print(
            f"  [{indice}/{total}] {pieza['codigo_pieza']:<4} "
            f"{pieza['nombre_pieza'][:17]:<18}"
            f"{buenas:>2}/{len(componente.cotas):<2} cotas   "
            f"{num(pieza['temperatura_c'], 2):>6} °C   {marca}"
        )

        if detallado or not ok:
            for cota in componente.cotas:
                medicion = medidas_por_cota[cota.codigo]
                if detallado or not medicion["ok"]:
                    color = VERDE if medicion["ok"] else ROJO
                    simbolo = "ok " if medicion["ok"] else ">>>"
                    texto = (
                        f"         {color}{simbolo}{RESET} {cota.codigo:<9} "
                        f"{num(medicion['valor'], cota.decimales):>12} {cota.unidad:<2}"
                        f"   [{num(cota.limite_inferior, cota.decimales)} – "
                        f"{num(cota.limite_superior, cota.decimales)}]"
                    )
                    if not medicion["ok"]:
                        texto += f"  {ROJO}{pieza['causa_defecto']}{RESET}"
                    print(texto)

    ensamble_ok = flujo.estado == "OK"
    color = VERDE if ensamble_ok else ROJO
    resumen = (
        f"{flujo.piezas_ok}/{total} piezas conformes"
        if ensamble_ok
        else f"{flujo.piezas_nok} de {total} piezas NOK · {flujo.causa_principal}"
    )
    print(
        f"  {GRIS}└──{RESET} ARMADO   {resumen:<44}"
        f"{color}{NEGRITA}ENSAMBLE {flujo.estado}{RESET}"
        + (
            f"   {GRIS}{num(tasa_acumulada * 100, 2)} % NOK acumulado{RESET}"
            if tasa_acumulada is not None
            else ""
        )
    )
    _ = flujo.cotas_nok  # disponible para quien consuma el objeto


def acumulado(linea: Linea) -> None:
    """Resumen de avance de la sesión actual."""
    flujos = linea.numero - linea.numero_inicial
    tasa_piezas = linea.total_nok / linea.total_piezas if linea.total_piezas else 0.0
    tasa_conjuntos = linea.total_conjuntos_nok / flujos if flujos else 0.0
    print()
    print(
        f"  {GRIS}── {flujos} flujos · {linea.total_piezas} piezas · "
        f"{linea.total_nok} NOK ({num(tasa_piezas * 100, 2)} %) · "
        f"{linea.total_conjuntos_nok} ensambles NOK "
        f"({num(tasa_conjuntos * 100, 2)} %) ──{RESET}"
    )


def error(mensaje: str) -> None:
    print(f"{ROJO}Error:{RESET} {mensaje}", file=sys.stderr)


def aviso(mensaje: str) -> None:
    print(f"{AMARILLO}Aviso:{RESET} {mensaje}", file=sys.stderr)


def informacion(mensaje: str) -> None:
    print(f"  {mensaje}")
