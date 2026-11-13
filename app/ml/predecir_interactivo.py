"""Inferencia y toma de decisiones sobre los datos más recientes.

Carga el modelo entrenado y, para cada pieza reciente, calcula el riesgo de
salir defectuosa ANTES de medirla (solo con covariables de máquina). Con ese
riesgo emite una decisión operativa de tres niveles:

    CONTINUAR          riesgo bajo, no hacer nada
    REVISAR PIEZA      riesgo medio, inspección adicional
    CAMBIAR HERRAMIENTA riesgo alto, intervención de mantenimiento

Además evalúa el conjunto de las últimas piezas: si la tendencia es alta,
recomienda el cambio de herramienta aunque ninguna pieza aislada lo dispare.

Uso:
    python predecir_interactivo.py
    python predecir_interactivo.py --ultimas 40
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from conexion_supabase import cargar_datos_tabla
from red_neuronal_ia import PreprocesadorDatosIA, RedNeuronalIA
from artefactos import ruta as ruta_artefacto

RUTA_MODELO = ruta_artefacto("modelo_supabase_ia.npz")
RUTA_ESTADO = ruta_artefacto("modelo_supabase_ia.json")

# Margen sobre el umbral para pasar de "revisar" a "intervenir".
MARGEN_ACTUAR = 0.15
# Cuántas piezas recientes se miran para la recomendación de mantenimiento.
VENTANA_TENDENCIA = 10000


def cargar_modelo():
    if not Path(RUTA_MODELO).exists() or not Path(RUTA_ESTADO).exists():
        print("No hay modelo entrenado. Ejecuta primero: python entrenar_con_supabase.py")
        return None, None, None
    estado = json.loads(Path(RUTA_ESTADO).read_text(encoding="utf-8"))
    red = RedNeuronalIA.cargar(RUTA_MODELO)
    pre = PreprocesadorDatosIA.desde_estado(estado["preprocesador"])
    return red, pre, estado


def decidir(probabilidad: float, umbral: float) -> str:
    if probabilidad >= min(0.95, umbral + MARGEN_ACTUAR):
        return "CAMBIAR HERRAMIENTA"
    if probabilidad >= umbral:
        return "REVISAR PIEZA"
    return "CONTINUAR"


def main() -> int:
    parser = argparse.ArgumentParser(description="Predicción y decisiones")
    parser.add_argument("--ultimas", type=int, default=20, help="Cuántas piezas analizar")
    parser.add_argument(
        "--con-ia",
        action="store_true",
        default=True,
        help="Ejecutar análisis detallado con IA y registrar recomendaciones en la base de datos (activo por defecto)",
    )
    parser.add_argument(
        "--sin-ia",
        action="store_false",
        dest="con_ia",
        help="No registrar en la base de datos",
    )
    args = parser.parse_args()

    red, pre, estado = cargar_modelo()
    if red is None:
        return 1

    umbral = float(estado.get("umbral", 0.5))
    print("=" * 74)
    print(" MODELO DE RIESGO — DECISIONES OPERATIVAS")
    print("=" * 74)
    print(f"Vista: {estado['tabla']} | umbral de decisión: {umbral:.2f}")

    tabla = cargar_datos_tabla(estado["tabla"])
    if len(tabla) == 0:
        print("No hay datos para predecir.")
        return 1

    X = pre.transformar_nuevos_datos(tabla)
    probabilidades = red.predecir_probabilidad(X).ravel()

    if hasattr(tabla, "columns"):
        columnas = list(tabla.columns)
        filas = tabla.values.tolist()
    else:
        columnas = tabla.columnas
        filas = tabla.filas

    i_desgaste = columnas.index("piezas_en_herramienta") if "piezas_en_herramienta" in columnas else None
    i_pieza = columnas.index("codigo_pieza") if "codigo_pieza" in columnas else None

    # Se ordenan por desgaste: las últimas son las de mayor riesgo potencial.
    if i_desgaste is not None:
        orden = sorted(range(len(filas)), key=lambda i: filas[i][i_desgaste] or 0)
    else:
        orden = list(range(len(filas)))
    seleccion = orden[-args.ultimas:]

    print(f"\n{'pieza':<10}{'desgaste':>9}{'riesgo':>9}   decisión")
    print("-" * 74)
    for i in seleccion:
        prob = float(probabilidades[i])
        desgaste = int(filas[i][i_desgaste] or 0) if i_desgaste is not None else 0
        pieza = str(filas[i][i_pieza]) if i_pieza is not None else f"item_{i}"
        print(f"{pieza:<10}{desgaste:>9}{prob * 100:>8.1f}%   {decidir(prob, umbral)}")

    # --- Decisión a nivel de herramienta --------------------------------
    ultimas = orden[-VENTANA_TENDENCIA:]
    riesgo_medio = sum(float(probabilidades[i]) for i in ultimas) / len(ultimas)
    desgaste_max = max(int(filas[i][i_desgaste] or 0) for i in ultimas) if i_desgaste is not None else 0
    alertas = sum(1 for i in ultimas if float(probabilidades[i]) >= umbral)

    print("\n" + "=" * 74)
    print(" RECOMENDACIÓN DE MANTENIMIENTO")
    print("=" * 74)
    print(f"Piezas consideradas      : {len(ultimas)}")
    print(f"Desgaste máximo          : {desgaste_max} piezas")
    print(f"Riesgo medio             : {riesgo_medio * 100:.1f} %")
    print(f"Piezas sobre el umbral   : {alertas}")

    if riesgo_medio >= 0.5 or alertas >= len(ultimas) * 0.5:
        print("\n ACCIÓN: cambiar la herramienta antes de seguir produciendo.")
        print(" Motivo: el riesgo agregado de las últimas piezas supera el umbral.")
    elif riesgo_medio >= umbral * 0.7:
        print("\n ACCIÓN: programar el cambio de herramienta en el próximo paro.")
        print(" Motivo: el riesgo está subiendo pero todavía no es crítico.")
    else:
        print("\n ACCIÓN: continuar. Sin señales de degradación.")
    print("=" * 74)

    if args.con_ia:
        import analisis_ia

        piezas_ia = int(os.getenv("IA_PIEZAS_EVALUAR", "1000"))
        print(f"\nIniciando análisis detallado con IA y recomendaciones ({piezas_ia} piezas)...")
        analisis_ia.ejecutar_analisis_completo(ultimas_piezas=piezas_ia, guardar=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
