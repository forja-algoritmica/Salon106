"""Entrena la red neuronal con los datos de Supabase.

Corrige tres problemas del esqueleto original:

1. **Desbalance de clases.** Con ~7 % de piezas rechazadas, un modelo que diga
   siempre "conforme" acierta el 93 % y parece bueno. Aquí se hace división
   estratificada y se sobremuestrea la clase minoritaria en entrenamiento.
2. **Fuga de información.** `v_entrenamiento_piezas` incluye las 82 medidas, así
   que el modelo aprende las tolerancias (útil para validar, inútil para
   predecir). Para anticipar el riesgo existe `v_riesgo_piezas`, que solo usa
   covariables de máquina.
3. **Modelo no reutilizable.** Antes se guardaban solo los pesos; ahora también
   se guarda el preprocesamiento, imprescindible para predecir.

Uso:
    python entrenar_con_supabase.py
    python entrenar_con_supabase.py --tabla v_riesgo_piezas
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np

from conexion_supabase import (
    cargar_datos_tabla,
    inspeccionar_tabla,
    listar_tablas_disponibles,
    tabla_por_defecto,
)
from red_neuronal_ia import PreprocesadorDatosIA, RedNeuronalIA, evaluar_metricas
from artefactos import ruta as ruta_artefacto

RUTA_MODELO = ruta_artefacto("modelo_supabase_ia.npz")
RUTA_ESTADO = ruta_artefacto("modelo_supabase_ia.json")


def dividir_estratificada(y: np.ndarray, fraccion_prueba: float = 0.2, semilla: int = 42):
    """Divide conservando la proporción de clases en ambos conjuntos."""
    rng = np.random.default_rng(semilla)
    indices_train: list[int] = []
    indices_prueba: list[int] = []
    for clase in np.unique(y):
        idx = np.flatnonzero(y.ravel() == clase)
        rng.shuffle(idx)
        corte = max(1, int(round(len(idx) * fraccion_prueba)))
        indices_prueba.extend(idx[:corte].tolist())
        indices_train.extend(idx[corte:].tolist())
    return np.array(indices_train), np.array(indices_prueba)


def dividir_tres(y: np.ndarray, semilla: int = 42):
    """60 % entrenamiento, 20 % validación (umbral), 20 % prueba (informe)."""
    idx_train, idx_resto = dividir_estratificada(y, fraccion_prueba=0.4, semilla=semilla)
    idx_val, idx_test = dividir_estratificada(
        y[idx_resto], fraccion_prueba=0.5, semilla=semilla + 1
    )
    return idx_train, idx_resto[idx_val], idx_resto[idx_test]


def elegir_umbral(prob: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """Busca el umbral que maximiza F1 en validación."""
    mejor = (0.5, 0.0, 0.0)
    for umbral in np.arange(0.30, 0.96, 0.05):
        pred = (prob >= umbral).astype(int)
        vp = int(np.sum((pred == 1) & (y.ravel() == 1)))
        fp = int(np.sum((pred == 1) & (y.ravel() == 0)))
        if vp == 0:
            continue
        precision = vp / (vp + fp) * 100
        recall = vp / y.sum() * 100
        f1 = 2 * precision * recall / (precision + recall)
        if f1 > mejor[1]:
            mejor = (float(umbral), f1, precision, recall)
    return mejor[0], mejor[2], mejor[3]


def sobremuestrear(X: np.ndarray, y: np.ndarray, semilla: int = 42):
    """Duplica la clase minoritaria para que el modelo no la ignore."""
    rng = np.random.default_rng(semilla)
    clases, cuentas = np.unique(y, return_counts=True)
    if len(clases) != 2:
        return X, y
    minoritaria = clases[np.argmin(cuentas)]
    mayoritaria = clases[np.argmax(cuentas)]
    idx_min = np.flatnonzero(y.ravel() == minoritaria)
    idx_may = np.flatnonzero(y.ravel() == mayoritaria)

    faltan = len(idx_may) - len(idx_min)
    if faltan <= 0:
        return X, y
    extra = rng.choice(idx_min, size=faltan, replace=True)
    indices = np.concatenate([np.arange(len(y)), extra])
    rng.shuffle(indices)
    return X[indices], y[indices]


def main() -> int:
    parser = argparse.ArgumentParser(description="Entrena el modelo con datos de Supabase")
    parser.add_argument(
        "--tabla",
        default=tabla_por_defecto(),
        help="Tabla o vista a usar (por defecto DB_TABLE o v_entrenamiento_piezas)",
    )
    parser.add_argument("--epocas", type=int, default=600)
    args = parser.parse_args()

    print("=" * 70)
    print(" ENTRENAMIENTO CON DATOS REALES DE SUPABASE")
    print("=" * 70)

    disponibles = listar_tablas_disponibles()
    if args.tabla not in disponibles:
        print(f"\n La tabla '{args.tabla}' no existe en el esquema.")
        print(f" Disponibles: {disponibles}")
        print(" Ejecuta primero: python ../tools/configurar_bd.py")
        return 1

    print(f"\n-> Usando: {args.tabla}")
    inspeccionar_tabla(args.tabla)

    tabla = cargar_datos_tabla(args.tabla)
    if len(tabla) < 50:
        print(f"\n Muy pocos registros ({len(tabla)}). Genera más datos con la línea.")
        return 1

    objetivo = os.getenv("DB_TARGET") or tabla.columnas[-1]
    print(f"\nVariable objetivo: '{objetivo}'")

    preprocesador = PreprocesadorDatosIA()
    X, y = preprocesador.ajustar_y_transformar(tabla, columna_target=objetivo)

    total = len(y)
    positivos = int(y.sum())
    print(
        f"\nClases: {positivos} no conformes de {total} "
        f"({positivos / total * 100:.2f} %)"
    )
    print(
        "Línea base (decir siempre 'conforme'): "
        f"{(total - positivos) / total * 100:.2f} % de exactitud"
    )

    idx_train, idx_val, idx_test = dividir_tres(y)
    X_train, y_train = X[idx_train], y[idx_train]
    X_val, y_val = X[idx_val], y[idx_val]
    X_test, y_test = X[idx_test], y[idx_test]
    print(
        f"Entrenamiento: {len(X_train)} (positivos {int(y_train.sum())}) | "
        f"Validación: {len(X_val)} (positivos {int(y_val.sum())}) | "
        f"Prueba: {len(X_test)} (positivos {int(y_test.sum())})"
    )

    X_train, y_train = sobremuestrear(X_train, y_train)
    print(f"Tras sobremuestreo: {len(X_train)} muestras equilibradas")

    red = RedNeuronalIA(
        n_entradas=X.shape[1],
        n_oculta1=min(32, max(8, X.shape[1] * 2)),
        n_oculta2=min(16, max(4, X.shape[1])),
        tasa_aprendizaje=0.03,
    )
    red.entrenar(X_train, y_train, epocas=args.epocas, verbose_cada=max(1, args.epocas // 4))

    print("\nSelección del umbral de decisión (sobre validación):")
    umbral, precision_val, recall_val = elegir_umbral(
        red.predecir_probabilidad(X_val).ravel(), y_val
    )
    print(
        f"  umbral elegido = {umbral:.2f} "
        f"(validación: precisión {precision_val:.1f} %, recall {recall_val:.1f} %)"
    )

    if len(X_test) and y_test.sum() > 0:
        print(f"\nInforme sobre el conjunto de prueba, con umbral {umbral:.2f}:")
        evaluar_metricas(y_test, red.predecir(X_test, umbral=umbral))

    red.guardar(RUTA_MODELO)
    Path(RUTA_ESTADO).write_text(
        json.dumps(
            {
                "tabla": args.tabla,
                "objetivo": objetivo,
                "umbral": umbral,
                "preprocesador": preprocesador.exportar_estado(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"Preprocesamiento guardado en: {RUTA_ESTADO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
