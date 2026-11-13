"""Motor de simulación del ensamble.

Genera `n` ensambles. Para cada ensamble se fabrica una unidad de cada
componente del catálogo, se miden todas sus cotas y se decide si la pieza y el
ensamble completo son conformes.

Causas de variación (todas configurables):
1. Variación natural del proceso, derivada del Cpk objetivo de cada cota.
2. Deriva por desgaste de herramienta dentro de cada ciclo de vida.
3. Eventos puntuales que desplazan varias cotas de la misma pieza.
4. Errores de medición del instrumento.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from .config import Componente, Config

PRIORIDAD_CAUSAS = (
    "evento_puntual",
    "error_medicion",
    "valor_atipico",
    "deriva_herramienta",
    "parametro_maquina",
    "variacion_proceso",
)
SIN_DEFECTO = "sin_defecto"
_RANGO_CAUSA = {causa: i for i, causa in enumerate(PRIORIDAD_CAUSAS)}


@dataclass
class Resultado:
    piezas: list[dict[str, Any]] = field(default_factory=list)
    mediciones: list[dict[str, Any]] = field(default_factory=list)
    conjuntos: list[dict[str, Any]] = field(default_factory=list)
    resumen: dict[str, Any] = field(default_factory=dict)


def _turno_de(fecha: datetime) -> str:
    """Turnos de 8 h que arrancan a las 06:00."""
    return f"T{((fecha.hour - 6) % 24) // 8 + 1}"


def _limitar(probabilidad: float) -> float:
    return float(min(max(probabilidad, 0.0), 1.0))


@dataclass
class _BloqueComponente:
    """Resultado interno de fabricar `n` unidades de un componente."""

    componente: Componente
    valores: dict[str, np.ndarray]
    reales: dict[str, np.ndarray]
    dentro: dict[str, np.ndarray]
    rango_causa: dict[str, np.ndarray]
    temperaturas: np.ndarray
    pos_vida: np.ndarray
    num_herramienta: np.ndarray
    pieza_ok: np.ndarray = field(default_factory=lambda: np.array([], dtype=bool))
    causa: np.ndarray = field(default_factory=lambda: np.array([], dtype=object))


def _generar_componente(
    componente: Componente,
    n: int,
    rng: np.random.Generator,
    config: Config,
    escala: float,
    indice_inicial: int = 0,
) -> _BloqueComponente:
    proceso = config.proceso
    defectos = config.defectos
    maquina = config.parametros

    k = np.arange(n, dtype=np.int64) + indice_inicial
    vida = max(int(proceso.vida_herramienta), 1)
    pos_vida = k % vida
    num_herramienta = k // vida
    desgaste = pos_vida / vida

    calentamiento = np.minimum(pos_vida, maquina.piezas_calentamiento) / max(
        maquina.piezas_calentamiento, 1
    )
    temperatura = (
        maquina.temperatura_ref
        + rng.normal(0.0, maquina.temperatura_sigma, n)
        + maquina.calentamiento_max * calentamiento
    )
    desvio_temperatura = temperatura - maquina.temperatura_ref

    z_comun = rng.standard_normal(n)
    hay_evento = rng.random(n) < _limitar(defectos.probabilidad_evento * escala)

    valores: dict[str, np.ndarray] = {}
    reales: dict[str, np.ndarray] = {}
    dentro: dict[str, np.ndarray] = {}
    rangos: dict[str, np.ndarray] = {}

    for cota in componente.cotas:
        sigma = cota.sigma_proceso * defectos.multiplicador_sigma

        # 1) Deriva por desgaste de herramienta.
        deriva = (
            cota.signo_deriva
            * cota.factor_deriva
            * defectos.deriva_total_sigmas
            * sigma
            * desgaste
        )

        # 2) Efecto de la temperatura de la estación (dilatación térmica).
        efecto_parametro = cota.sensibilidad.get("temperatura", 0.0) * desvio_temperatura

        media = cota.nominal + cota.sesgo + deriva + efecto_parametro

        # 3) Variación natural + causa común compartida entre cotas.
        ruido = rng.normal(0.0, sigma, n) + cota.carga_comun * sigma * z_comun

        # 4) Evento puntual: varias cotas de la misma pieza se desplazan.
        afectada_evento = hay_evento & (
            rng.random(n) < _limitar(defectos.probabilidad_cota_en_evento)
        )
        evento = np.where(
            afectada_evento,
            rng.uniform(defectos.sigmas_evento_min, defectos.sigmas_evento_max, n)
            * sigma
            * rng.choice(np.array([-1.0, 1.0]), n),
            0.0,
        )

        # 5) Valor atípico aislado.
        afectada_atipico = rng.random(n) < _limitar(defectos.probabilidad_base * escala)
        atipico = np.where(
            afectada_atipico,
            rng.uniform(defectos.sigmas_atipico_min, defectos.sigmas_atipico_max, n)
            * sigma
            * rng.choice(np.array([-1.0, 1.0]), n),
            0.0,
        )

        valor_real = media + ruido + evento + atipico

        # 6) Medición: ruido del instrumento y fallos esporádicos del equipo.
        valor_medido = valor_real + rng.normal(0.0, cota.sigma_medicion, n)
        fallo_medicion = rng.random(n) < _limitar(
            defectos.probabilidad_error_medicion * escala
        )
        valor_medido = valor_medido + np.where(
            fallo_medicion,
            rng.uniform(defectos.error_bandas_min, defectos.error_bandas_max, n)
            * cota.banda
            * rng.choice(np.array([-1.0, 1.0]), n),
            0.0,
        )

        if cota.solo_positivo:
            valor_real = np.clip(valor_real, 0.0, None)
            valor_medido = np.clip(valor_medido, 0.0, None)

        valor_medido = np.round(valor_medido, cota.decimales)
        esta_dentro = (valor_medido >= cota.limite_inferior) & (
            valor_medido <= cota.limite_superior
        )

        # Etiqueta de causa, de menor a mayor prioridad (la última gana).
        rango = np.where(esta_dentro, 99, 5).astype(np.int8)

        media_solo_parametro = cota.nominal + cota.sesgo + efecto_parametro
        rango = np.where(
            ~esta_dentro
            & (
                (media_solo_parametro < cota.limite_inferior)
                | (media_solo_parametro > cota.limite_superior)
            ),
            4,
            rango,
        )

        if np.any(deriva):
            recorrido = np.where(valor_medido > cota.nominal, cota.tol_sup, -cota.tol_inf)
            rango = np.where(~esta_dentro & (np.abs(deriva) >= 0.25 * recorrido), 3, rango)

        rango = np.where(~esta_dentro & afectada_atipico, 2, rango)
        rango = np.where(~esta_dentro & fallo_medicion, 1, rango)
        rango = np.where(~esta_dentro & afectada_evento, 0, rango)

        valores[cota.codigo] = valor_medido
        reales[cota.codigo] = valor_real
        dentro[cota.codigo] = esta_dentro
        rangos[cota.codigo] = rango

    bloque = _BloqueComponente(
        componente=componente,
        valores=valores,
        reales=reales,
        dentro=dentro,
        rango_causa=rangos,
        temperaturas=temperatura,
        pos_vida=pos_vida,
        num_herramienta=num_herramienta,
    )

    matriz_dentro = np.vstack([dentro[c.codigo] for c in componente.cotas])
    bloque.pieza_ok = matriz_dentro.all(axis=0)

    matriz_rango = np.vstack([rangos[c.codigo] for c in componente.cotas])
    mejor = matriz_rango.min(axis=0)
    causas = np.array(
        [PRIORIDAD_CAUSAS[r] if r < len(PRIORIDAD_CAUSAS) else SIN_DEFECTO for r in mejor],
        dtype=object,
    )
    bloque.causa = np.where(bloque.pieza_ok, SIN_DEFECTO, causas)
    return bloque


def generar(
    config: Config,
    conjuntos: int | None = None,
    semilla: int | None = None,
    escala_defectos: float | None = None,
) -> Resultado:
    """Genera el histórico de producción de `conjuntos` ensambles."""
    proceso = config.proceso
    defectos = config.defectos

    n = int(proceso.conjuntos if conjuntos is None else conjuntos)
    if n <= 0:
        raise ValueError("'conjuntos' debe ser mayor que 0")

    semilla = proceso.semilla if semilla is None else semilla
    escala = defectos.escala if escala_defectos is None else float(escala_defectos)
    if escala < 0:
        raise ValueError("'escala_defectos' no puede ser negativa")

    rng = np.random.default_rng(semilla)

    # --- Tiempo de cada ensamble -----------------------------------------
    ciclo = np.maximum(
        proceso.tiempo_ciclo_seg + rng.normal(0.0, proceso.tiempo_ciclo_sigma, n), 60.0
    )
    inicio_seg = np.cumsum(ciclo) - ciclo
    t0 = datetime.fromisoformat(proceso.inicio)
    fechas = [t0 + timedelta(seconds=float(s)) for s in inicio_seg]

    # --- Fabricación de cada componente -----------------------------------
    bloques = [
        _generar_componente(componente, n, rng, config, escala)
        for componente in config.componentes
    ]

    # --- Tablas -----------------------------------------------------------
    piezas: list[dict[str, Any]] = []
    mediciones: list[dict[str, Any]] = []
    conjuntos: list[dict[str, Any]] = []

    for i in range(n):
        fecha = fechas[i]
        marca = fecha.strftime("%Y-%m-%d %H:%M:%S")
        turno = _turno_de(fecha)
        operador = proceso.operadores[
            (fecha.toordinal() + int(turno[1:])) % len(proceso.operadores)
        ]
        lote = f"L-{i // proceso.tamano_lote + 1:04d}"
        id_conjunto = f"CJ-{i + 1:05d}"

        causas_conjunto: list[str] = []
        cotas_nok_conjunto = 0
        piezas_nok = 0
        piezas_ok = 0

        for bloque in bloques:
            componente = bloque.componente
            dentro = bloque.pieza_ok[i]
            causa = str(bloque.causa[i])
            ok_cotas = [
                c.codigo for c in componente.cotas if not bloque.dentro[c.codigo][i]
            ]

            if dentro:
                piezas_ok += 1
            else:
                piezas_nok += 1
                causas_conjunto.append(causa)
                cotas_nok_conjunto += len(ok_cotas)

            piezas.append(
                {
                    "id_conjunto": id_conjunto,
                    "marca_tiempo": marca,
                    "fecha": fecha.strftime("%Y-%m-%d"),
                    "turno": turno,
                    "operador": operador,
                    "lote": lote,
                    "linea": proceso.linea,
                    "estacion": componente.codigo,
                    "id_pieza": componente.id,
                    "codigo_pieza": componente.codigo,
                    "nombre_pieza": componente.nombre,
                    "serie_pieza": f"{componente.codigo}-{i + 1:06d}",
                    "id_herramienta": f"H-{componente.codigo}-{bloque.num_herramienta[i] + 1:04d}",
                    "piezas_en_herramienta": int(bloque.pos_vida[i]),
                    "temperatura_c": round(float(bloque.temperaturas[i]), 2),
                    "n_cotas_nok": len(ok_cotas),
                    "cotas_nok": "|".join(ok_cotas),
                    "estado": "OK" if dentro else "NOK",
                    "causa_defecto": causa,
                    "etiqueta": 0 if dentro else 1,
                }
            )

            if config.salida.incluir_mediciones:
                for cota in componente.cotas:
                    valor = float(bloque.valores[cota.codigo][i])
                    mediciones.append(
                        {
                            "id_conjunto": id_conjunto,
                            "id_pieza": componente.id,
                            "codigo_pieza": componente.codigo,
                            "serie_pieza": f"{componente.codigo}-{i + 1:06d}",
                            "codigo_cota": cota.codigo,
                            "nombre_cota": cota.nombre,
                            "tipo": cota.tipo,
                            "unidad": cota.unidad,
                            "nominal": cota.nominal,
                            "limite_inferior": round(cota.limite_inferior, 6),
                            "limite_superior": round(cota.limite_superior, 6),
                            "valor": valor,
                            "desviacion": round(valor - cota.nominal, 6),
                            "ok": 1 if bloque.dentro[cota.codigo][i] else 0,
                        }
                    )

        causa_principal = (
            min(causas_conjunto, key=lambda c: _RANGO_CAUSA.get(c, 99))
            if causas_conjunto
            else SIN_DEFECTO
        )
        conjuntos.append(
            {
                "id_conjunto": id_conjunto,
                "marca_tiempo": marca,
                "fecha": fecha.strftime("%Y-%m-%d"),
                "turno": turno,
                "operador": operador,
                "lote": lote,
                "linea": proceso.linea,
                "piezas_ok": piezas_ok,
                "piezas_nok": piezas_nok,
                "cotas_nok": cotas_nok_conjunto,
                "causa_principal": causa_principal,
                "estado": "OK" if piezas_nok == 0 else "NOK",
                "etiqueta": 0 if piezas_nok == 0 else 1,
            }
        )

    resumen = _resumen(
        config, bloques, piezas, conjuntos, n, semilla, escala
    )
    return Resultado(piezas=piezas, mediciones=mediciones, conjuntos=conjuntos, resumen=resumen)


def _resumen(
    config: Config,
    bloques: list[_BloqueComponente],
    piezas: list[dict[str, Any]],
    conjuntos: list[dict[str, Any]],
    n: int,
    semilla: int | None,
    escala: float,
) -> dict[str, Any]:
    total_piezas = len(piezas)
    nok_piezas = sum(p["etiqueta"] for p in piezas)
    nok_conjuntos = sum(c["etiqueta"] for c in conjuntos)

    por_causa: dict[str, int] = {}
    for p in piezas:
        if p["etiqueta"]:
            por_causa[p["causa_defecto"]] = por_causa.get(p["causa_defecto"], 0) + 1

    por_pieza = []
    for bloque in bloques:
        componente = bloque.componente
        nok = int((~bloque.pieza_ok).sum())
        cpks = []
        for cota in componente.cotas:
            mediciones = bloque.reales[cota.codigo]
            sigma = float(np.std(mediciones, ddof=1)) if n > 1 else 0.0
            if sigma > 0:
                media = float(np.mean(mediciones))
                cpks.append(
                    min(
                        cota.limite_superior - media, media - cota.limite_inferior
                    )
                    / (3.0 * sigma)
                )
        por_pieza.append(
            {
                "codigo_pieza": componente.codigo,
                "nombre_pieza": componente.nombre,
                "cotas": len(componente.cotas),
                "piezas": n,
                "nok": nok,
                "tasa_nok": round(nok / n, 6),
                "cpk_min": round(min(cpks), 3) if cpks else 0.0,
            }
        )

    por_cota = []
    for bloque in bloques:
        componente = bloque.componente
        for cota in componente.cotas:
            mediciones = bloque.reales[cota.codigo]
            media = float(np.mean(mediciones))
            sigma = float(np.std(mediciones, ddof=1)) if n > 1 else 0.0
            limite_inf = cota.limite_inferior
            limite_sup = cota.limite_superior
            if sigma > 0:
                cp = cota.banda / (6.0 * sigma)
                cpk = min(limite_sup - media, media - limite_inf) / (3.0 * sigma)
            else:
                cp = cpk = float("nan")
            nok = int((~bloque.dentro[cota.codigo]).sum())
            por_cota.append(
                {
                    "codigo_cota": cota.codigo,
                    "codigo_pieza": componente.codigo,
                    "nombre": cota.nombre,
                    "tipo": cota.tipo,
                    "unidad": cota.unidad,
                    "nominal": cota.nominal,
                    "limite_inferior": round(limite_inf, 6),
                    "limite_superior": round(limite_sup, 6),
                    "media": round(media, 6),
                    "sigma": round(sigma, 6),
                    "cp": round(cp, 3),
                    "cpk": round(cpk, 3),
                    "nok": nok,
                    "tasa_nok": round(nok / n, 6),
                }
            )

    peores = sorted(por_cota, key=lambda f: (-f["tasa_nok"], f["cpk"]))[:10]

    return {
        "conjuntos": n,
        "componentes_por_conjunto": len(config.componentes),
        "piezas_fabricadas": total_piezas,
        "cotas_por_conjunto": sum(len(b.componente.cotas) for b in bloques),
        "piezas_ok": total_piezas - nok_piezas,
        "piezas_nok": nok_piezas,
        "tasa_nok": round(nok_piezas / total_piezas, 6) if total_piezas else 0.0,
        "conjuntos_ok": n - nok_conjuntos,
        "conjuntos_nok": nok_conjuntos,
        "tasa_conjuntos_nok": round(nok_conjuntos / n, 6),
        "por_causa": dict(sorted(por_causa.items(), key=lambda kv: -kv[1])),
        "por_pieza": por_pieza,
        "por_cota": por_cota,
        "peores_cotas": peores,
        "semilla": semilla,
        "escala_defectos": round(escala, 6),
    }


def calibrar_escala(
    config: Config,
    tasa_objetivo: float,
    conjuntos: int | None = None,
    semilla: int | None = None,
    iteraciones: int = 14,
    nivel: str = "piezas",
) -> float:
    """Ajusta `defectos.escala` por bisección para acercarse a una tasa objetivo.

    `nivel` indica qué se mide: "piezas" (componentes sueltos) o "conjuntos"
    (ensambles completos, que fallan si falla cualquiera de sus piezas).

    Solo escala las causas especiales. La variación natural y la deriva por
    desgaste no se ven afectadas: si por sí solas ya superan el objetivo, se
    devuelve 0.0.
    """
    if nivel not in ("piezas", "conjuntos"):
        raise ValueError("'nivel' debe ser 'piezas' o 'conjuntos'")
    if not 0.0 <= tasa_objetivo <= 1.0:
        raise ValueError("'tasa_objetivo' debe estar entre 0 y 1")

    clave = "tasa_nok" if nivel == "piezas" else "tasa_conjuntos_nok"

    def tasa_con(escala: float) -> float:
        return generar(
            config, conjuntos=conjuntos, semilla=semilla, escala_defectos=escala
        ).resumen[clave]

    if tasa_con(0.0) >= tasa_objetivo:
        return 0.0

    bajo, alto = 0.0, 1.0
    for _ in range(6):
        if tasa_con(alto) >= tasa_objetivo:
            break
        alto *= 4.0
    else:
        return alto

    for _ in range(iteraciones):
        medio = (bajo + alto) / 2.0
        if tasa_con(medio) < tasa_objetivo:
            bajo = medio
        else:
            alto = medio
    return round((bajo + alto) / 2.0, 6)
