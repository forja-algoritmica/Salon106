"""Rutas de trabajo que funcionan igual como script y como .exe."""

from __future__ import annotations

import sys
from pathlib import Path


def carpeta_base() -> Path:
    """Carpeta de referencia: junto al ejecutable o la raíz del proyecto."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resolver(ruta: str | Path) -> Path:
    """Convierte una ruta relativa en absoluta respecto a la carpeta base."""
    camino = Path(ruta)
    return camino if camino.is_absolute() else carpeta_base() / camino
