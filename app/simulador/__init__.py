"""Simulador del ensamble del brazo de retroexcavadora.

Uso rápido::

    from simulador import config_por_defecto, generar, guardar_resultado

    config = config_por_defecto()
    resultado = generar(config, conjuntos=200)
    guardar_resultado(resultado, config)
"""

from .config import (
    Componente,
    Config,
    Cota,
    Defectos,
    ParametrosMaquina,
    Proceso,
    Salida,
    cargar_config,
    config_por_defecto,
    guardar_config,
)
from .exportacion import guardar_resultado
from .generador import Resultado, calibrar_escala, generar

__all__ = [
    "Componente",
    "Config",
    "Cota",
    "Defectos",
    "ParametrosMaquina",
    "Proceso",
    "Resultado",
    "Salida",
    "calibrar_escala",
    "cargar_config",
    "config_por_defecto",
    "generar",
    "guardar_config",
    "guardar_resultado",
]

__version__ = "0.2.0"
