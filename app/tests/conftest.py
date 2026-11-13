"""Configuración de pytest: deja `app/` y `ml/` en el path de importación."""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

for subcarpeta in ("app", "ml"):
    ruta = str(RAIZ / subcarpeta)
    if ruta not in sys.path:
        sys.path.insert(0, ruta)
