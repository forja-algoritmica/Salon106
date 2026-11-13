"""Línea de ensamble continua.

Cada llamada a `Linea.siguiente_flujo()` produce un ensamble completo: pasa por
todas las estaciones (una por componente) midiendo cada pieza, y cierra el
flujo con el veredicto del conjunto. Al terminar, la línea queda lista para
empezar el siguiente flujo con los mismos procesos, conservando el desgaste de
herramientas, los contadores y el reloj.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from .config import Config
from .generador import (
    PRIORIDAD_CAUSAS,
    SIN_DEFECTO,
    _BloqueComponente,
    _generar_componente,
    _turno_de,
)

_RANGO_CAUSA = {causa: i for i, causa in enumerate(PRIORIDAD_CAUSAS)}


@dataclass
class Flujo:
    """Un ensamble completo terminado."""

    id_flujo: str
    numero: int
    iniciado_en: datetime
    cerrado_en: datetime
    linea: str
    turno: str
    operador: str
    lote: str
    piezas: list[dict[str, Any]] = field(default_factory=list)
    mediciones: list[dict[str, Any]] = field(default_factory=list)

    @property
    def piezas_ok(self) -> int:
        return sum(1 for p in self.piezas if p["estado"] == "OK")

    @property
    def piezas_nok(self) -> int:
        return sum(1 for p in self.piezas if p["estado"] == "NOK")

    @property
    def cotas_nok(self) -> int:
        return sum(p["n_cotas_nok"] for p in self.piezas)

    @property
    def causa_principal(self) -> str:
        causas = [p["causa_defecto"] for p in self.piezas if p["estado"] == "NOK"]
        if not causas:
            return SIN_DEFECTO
        return min(causas, key=lambda c: _RANGO_CAUSA.get(c, 99))

    @property
    def estado(self) -> str:
        return "OK" if self.piezas_nok == 0 else "NOK"

    def como_registro(self) -> dict[str, Any]:
        return {
            "id_flujo": self.id_flujo,
            "iniciado_en": self.iniciado_en,
            "cerrado_en": self.cerrado_en,
            "linea": self.linea,
            "turno": self.turno,
            "operador": self.operador,
            "lote": self.lote,
            "piezas_ok": self.piezas_ok,
            "piezas_nok": self.piezas_nok,
            "cotas_nok": self.cotas_nok,
            "causa_principal": self.causa_principal,
            "estado": self.estado,
        }


class Linea:
    """Estado vivo de la línea: reloj, contadores de herramienta y RNG."""

    def __init__(
        self,
        config: Config,
        semilla: int | None = None,
        escala_defectos: float | None = None,
        numero_inicial: int = 0,
        contadores: dict[str, int] | None = None,
        reloj_inicial: datetime | None = None,
    ) -> None:
        self.config = config
        semilla_base = config.proceso.semilla if semilla is None else semilla
        if semilla_base is None and numero_inicial == 0:
            self.rng = np.random.default_rng()
        else:
            # Al retomar una corrida se cambia la secuencia para no repetir
            # exactamente los mismos números aleatorios.
            self.rng = np.random.default_rng([int(semilla_base or 0), int(numero_inicial)])
        self.escala = (
            config.defectos.escala if escala_defectos is None else float(escala_defectos)
        )
        self.reloj = reloj_inicial or datetime.fromisoformat(config.proceso.inicio)
        self.numero_inicial = int(numero_inicial)
        self.numero = int(numero_inicial)
        self.reloj_real = getattr(config.proceso, "reloj", "simulado") == "real"
        self.contadores: dict[str, int] = {c.codigo: 0 for c in config.componentes}
        if contadores:
            self.contadores.update(contadores)
        # Acumulados para el resumen de pantalla.
        self.total_piezas = 0
        self.total_nok = 0
        self.total_conjuntos_nok = 0

    # ------------------------------------------------------------------
    @property
    def paso_estacion(self) -> timedelta:
        """Tiempo de cada estación: el ciclo repartido entre estaciones + armado."""
        estaciones = len(self.config.componentes) + 1
        return timedelta(seconds=self.config.proceso.tiempo_ciclo_seg / estaciones)

    def siguiente_flujo(self) -> Flujo:
        """Fabrica un ensamble completo, estación por estación."""
        self.numero += 1
        id_flujo = f"FL-{self.numero:06d}"
        inicio = datetime.now() if self.reloj_real else self.reloj

        flujo = Flujo(
            id_flujo=id_flujo,
            numero=self.numero,
            iniciado_en=inicio,
            cerrado_en=inicio,
            linea=self.config.proceso.linea,
            turno=_turno_de(inicio),
            operador=self._operador(inicio),
            lote=f"L-{(self.numero - 1) // self.config.proceso.tamano_lote + 1:04d}",
        )

        for indice, componente in enumerate(self.config.componentes):
            posicion = self.contadores[componente.codigo]
            bloque = _generar_componente(
                componente,
                1,
                self.rng,
                self.config,
                self.escala,
                indice_inicial=posicion,
            )
            self.contadores[componente.codigo] = posicion + 1

            if self.reloj_real:
                # Hora real en cada estación: el orden lo da la propia marca
                # de tiempo, sin adelantar el reloj.
                momento = datetime.now()
            else:
                self.reloj += self.paso_estacion
                momento = self.reloj

            flujo.piezas.append(
                self._registro_pieza(componente, bloque, id_flujo, momento)
            )
            flujo.mediciones.extend(
                self._registro_mediciones(componente, bloque, id_flujo)
            )

        # Estación de armado final.
        if self.reloj_real:
            flujo.cerrado_en = datetime.now()
        else:
            self.reloj += self.paso_estacion
            flujo.cerrado_en = self.reloj

        self.total_piezas += len(flujo.piezas)
        self.total_nok += flujo.piezas_nok
        self.total_conjuntos_nok += 1 if flujo.estado == "NOK" else 0
        return flujo

    # ------------------------------------------------------------------
    def _operador(self, momento: datetime) -> str:
        operadores = self.config.proceso.operadores
        return operadores[(momento.toordinal() + int(_turno_de(momento)[1:])) % len(operadores)]

    def _registro_pieza(
        self,
        componente: Any,
        bloque: _BloqueComponente,
        id_flujo: str,
        momento: datetime,
    ) -> dict[str, Any]:
        ok = bool(bloque.pieza_ok[0])
        cotas_mal = [
            cota.codigo for cota in componente.cotas if not bloque.dentro[cota.codigo][0]
        ]
        return {
            "id_flujo": id_flujo,
            "codigo_pieza": componente.codigo,
            "nombre_pieza": componente.nombre,
            "serie_pieza": f"{componente.codigo}-{self.contadores[componente.codigo]:06d}",
            "estacion": componente.codigo,
            "fabricado_en": momento,
            "temperatura_c": round(float(bloque.temperaturas[0]), 2),
            "id_herramienta": f"H-{componente.codigo}-{bloque.num_herramienta[0] + 1:04d}",
            "piezas_en_herramienta": int(bloque.pos_vida[0]),
            "n_cotas_nok": len(cotas_mal),
            "cotas_nok": "|".join(cotas_mal),
            "causa_defecto": str(bloque.causa[0]),
            "estado": "OK" if ok else "NOK",
            "etiqueta": 0 if ok else 1,
        }

    def _registro_mediciones(
        self, componente: Any, bloque: _BloqueComponente, id_flujo: str
    ) -> list[dict[str, Any]]:
        serie = f"{componente.codigo}-{self.contadores[componente.codigo]:06d}"
        filas = []
        for cota in componente.cotas:
            valor = float(bloque.valores[cota.codigo][0])
            filas.append(
                {
                    "id_flujo": id_flujo,
                    "codigo_pieza": componente.codigo,
                    "serie_pieza": serie,
                    "codigo_cota": cota.codigo,
                    "nombre_cota": cota.nombre,
                    "unidad": cota.unidad,
                    "nominal": cota.nominal,
                    "limite_inferior": round(cota.limite_inferior, 4),
                    "limite_superior": round(cota.limite_superior, 4),
                    "valor": valor,
                    "desviacion": round(valor - cota.nominal, 4),
                    "ok": bool(bloque.dentro[cota.codigo][0]),
                }
            )
        return filas
