"""Ruta donde el servicio de ML guarda sus artefactos (modelo, umbral, detector).

En el contenedor el sistema de archivos es de solo lectura
(`read_only: true` en docker-compose), así que los artefactos deben ir a un
volumen. La ruta se controla con la variable ML_DIR_ARTEFACTOS.

En local, sin la variable, se usa el directorio actual.
"""

from __future__ import annotations

import os
from pathlib import Path


def directorio() -> Path:
    ruta = Path(os.getenv("ML_DIR_ARTEFACTOS", "."))
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def ruta(nombre: str) -> Path:
    return directorio() / nombre
