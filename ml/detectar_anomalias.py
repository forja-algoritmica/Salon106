"""Detección de anomalías SIN etiquetas.

Detecta piezas "raras" aunque estén dentro de tolerancia, usando solo las
mediciones. Sirve cuando no hay histórico de rechazos: se aprende cómo luce una
pieza normal y se marca lo que se aleja del patrón.

Método: puntaje z por cota, ajustado solo con las piezas conformes.

    z_i = (valor_i - media_i) / desviacion_i

    puntaje de la pieza = max |z_i|   (la cota más rara)
    y también el RMS de los z, que detecta piezas desplazadas en varias cotas.

El umbral se fija con un percentil de la propia población conforme, de modo que
se espere un porcentaje bajo de falsas alarmas.

Uso:
    python detectar_anomalias.py
    python detectar_anomalias.py --percentil 99.5
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from conexion_supabase import cargar_datos_tabla
from artefactos import ruta as ruta_artefacto

RUTA_ESTADO = Path("modelo_supabase_ia.json")


def columnas_cotas(tabla) -> list[str]:
    return [c for c in tabla.columnas if c.startswith("cota_")]


def matriz_cotas(tabla, columnas: list[str]) -> np.ndarray:
    indices = [tabla.columnas.index(c) for c in columnas]
    filas = []
    for fila in tabla.filas:
        filas.append([float(fila[i]) if fila[i] is not None else np.nan for i in indices])
    return np.array(filas, dtype=np.float64)


def ajustar(X: np.ndarray, mascara_conforme: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Media y desviación por cota, calculadas solo con piezas conformes."""
    base = X[mascara_conforme]
    media = np.nanmedian(base, axis=0)
    desviacion = np.nanstd(base, axis=0)
    desviacion[desviacion == 0] = 1.0
    return media, desviacion


def puntajes(X: np.ndarray, media: np.ndarray, desviacion: np.ndarray):
    z = (X - media) / desviacion
    z = np.nan_to_num(z, nan=0.0)
    return np.abs(z).max(axis=1), np.sqrt((z**2).mean(axis=1))


def main() -> int:
    parser = argparse.ArgumentParser(description="Detección de anomalías sin etiquetas")
    parser.add_argument("--tabla", default="v_entrenamiento_piezas")
    parser.add_argument(
        "--percentil",
        type=float,
        default=99.5,
        help="Percentil de la población conforme usado como umbral",
    )
    args = parser.parse_args()

    print("=" * 70)
    print(" DETECCIÓN DE ANOMALÍAS (sin usar la etiqueta)")
    print("=" * 70)

    tabla = cargar_datos_tabla(args.tabla)
    if len(tabla) < 100:
        print("Muy pocos datos. Genera más piezas con la línea.")
        return 1

    columnas = columnas_cotas(tabla)
    if not columnas:
        print("La vista no tiene columnas 'cota_*'. Usa v_entrenamiento_piezas.")
        return 1

    X = matriz_cotas(tabla, columnas)
    i_objetivo = tabla.columnas.index("defectuosa")
    y = np.array([float(f[i_objetivo]) for f in tabla.filas])
    conforme = y == 0

    media, desviacion = ajustar(X, conforme)
    max_z, rms_z = puntajes(X, media, desviacion)

    umbral_max = float(np.percentile(max_z[conforme], args.percentil))
    umbral_rms = float(np.percentile(rms_z[conforme], args.percentil))

    alarma = (max_z >= umbral_max) | (rms_z >= umbral_rms)

    print(f"\nPiezas analizadas       : {len(X)}  ({int(conforme.sum())} conformes)")
    print(f"Cotas consideradas      : {len(columnas)}")
    print(f"Umbral max|z| ({args.percentil} %)  : {umbral_max:.2f}")
    print(f"Umbral RMS z            : {umbral_rms:.2f}")

    # Capacidad de la alarma frente al desenlace real
    vp = int(np.sum(alarma & (y == 1)))
    fp = int(np.sum(alarma & (y == 0)))
    fn = int(np.sum(~alarma & (y == 1)))
    recall = vp / (vp + fn) * 100 if (vp + fn) else 0
    precision = vp / (vp + fp) * 100 if (vp + fp) else 0

    print("\nResultado de la alarma:")
    print(f"  anomalías marcadas      : {int(alarma.sum())}")
    print(f"  defectos detectados     : {vp} de {vp + fn} (recall {recall:.1f} %)")
    print(f"  falsas alarmas          : {fp} (precisión {precision:.1f} %)")

    # Valor real del enfoque no supervisado: piezas buenas pero raras
    raras_ok = int(np.sum(alarma & (y == 0)))
    print(f"\nPiezas conformes pero atípicas: {raras_ok}")
    print("  Son candidatas a revisión aunque cumplan tolerancia (aviso temprano).")

    # Guardar el estado del detector
    estado = {
        "tabla": args.tabla,
        "columnas": columnas,
        "media": media.tolist(),
        "desviacion": desviacion.tolist(),
        "umbral_max_z": umbral_max,
        "umbral_rms_z": umbral_rms,
        "percentil": args.percentil,
    }
    ruta_artefacto("detector_anomalias.json").write_text(
        json.dumps(estado, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\nDetector guardado en: detector_anomalias.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
