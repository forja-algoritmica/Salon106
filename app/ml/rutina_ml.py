"""Rutina automática del servicio `ml` (la que espera el Dockerfile).

Entrena una vez si no hay modelo y luego repite la predicción cada cierto
intervalo, de modo que el contenedor no termina y `restart: unless-stopped`
no lo reinicia en bucle.
"""

from __future__ import annotations

import os
import time
import traceback
from pathlib import Path

import analisis_ia
import entrenar_con_supabase as entrenamiento
import predecir_interactivo as prediccion

INTERVALO = int(os.getenv("INTERVALO_ML_SEGUNDOS", "600"))
OBJETIVO_ENTRENAMIENTO = int(os.getenv("ENTRENAR_CADA_SEGUNDOS", "0"))  # 0 = solo una vez
HABILITAR_ANALISIS_IA = os.getenv("HABILITAR_ANALISIS_IA", "1").lower() not in ("0", "false", "no")

if __name__ == "__main__":
    ultimo_entrenamiento = 0.0
    while True:
        try:
            necesita = not Path(entrenamiento.RUTA_MODELO).exists()
            toca = OBJETIVO_ENTRENAMIENTO and (
                time.time() - ultimo_entrenamiento >= OBJETIVO_ENTRENAMIENTO
            )
            if necesita or toca:
                print("\n[ml] Entrenando modelo ...")
                entrenamiento.main()
                ultimo_entrenamiento = time.time()

            print("\n[ml] Generando inferencia operativa...")
            prediccion.main()

            if HABILITAR_ANALISIS_IA:
                print("\n[ml] Ejecutando análisis detallado con IA y recomendaciones...")
                analisis_ia.ejecutar_analisis_completo(guardar=True)
        except Exception:
            print("[ml] Error en el ciclo:")
            traceback.print_exc()

        print(f"\n[ml] Esperando {INTERVALO} s para el siguiente ciclo ...")
        time.sleep(INTERVALO)
