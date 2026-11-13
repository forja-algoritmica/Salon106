"""Calcula las decisiones del modelo y las guarda en la base.

Para cada pieza inspeccionada estima el riesgo con las covariables de máquina
(desgaste, temperatura, hora) y registra la decisión en `calidad_piezas.decisiones`:

    CONTINUAR | REVISAR PIEZA | CAMBIAR HERRAMIENTA

Es un proceso por lote: se ejecuta después de generar datos. Deja la tabla
lista para el tablero y para auditar por qué se intervino una pieza.

Uso:
    python registrar_decisiones.py
    python registrar_decisiones.py --reemplazar
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from artefactos import ruta as ruta_artefacto
from conexion_supabase import consultar, obtener_conexion
from predecir_interactivo import decidir
from red_neuronal_ia import PreprocesadorDatosIA, RedNeuronalIA

RUTA_MODELO = ruta_artefacto("modelo_supabase_ia.npz")
RUTA_ESTADO = ruta_artefacto("modelo_supabase_ia.json")
TAMANO_LOTE = 500


def cargar_modelo():
    if not Path(RUTA_MODELO).exists() or not Path(RUTA_ESTADO).exists():
        print("No hay modelo entrenado. Ejecuta: python entrenar_con_supabase.py")
        return None, None, None
    estado = json.loads(Path(RUTA_ESTADO).read_text(encoding="utf-8"))
    red = RedNeuronalIA.cargar(str(RUTA_MODELO))
    pre = PreprocesadorDatosIA.desde_estado(estado["preprocesador"])
    return red, pre, estado


def motivo(decision: str, probabilidad: float, umbral: float, desgaste: int) -> str:
    if decision == "CONTINUAR":
        return "riesgo bajo"
    if decision == "REVISAR PIEZA":
        return f"riesgo {probabilidad * 100:.1f}% sobre el umbral {umbral * 100:.1f}%"
    return f"riesgo {probabilidad * 100:.1f}% con desgaste {desgaste} piezas"


def guardar(filas: list[tuple]) -> int:
    """Inserta en lotes de 500 filas (evita miles de viajes de red)."""
    con = obtener_conexion()
    insertadas = 0
    try:
        cur = con.cursor()
        for inicio in range(0, len(filas), TAMANO_LOTE):
            lote = filas[inicio : inicio + TAMANO_LOTE]
            valores = ", ".join(["(%s, %s, %s, %s, %s, %s)"] * len(lote))
            parametros = [valor for fila in lote for valor in fila]
            cur.execute(
                "INSERT INTO calidad_piezas.decisiones"
                " (id_revision, probabilidad, umbral, decision, motivo, modelo)"
                f" VALUES {valores}"
                " ON CONFLICT (id_revision) DO UPDATE SET"
                " probabilidad = EXCLUDED.probabilidad,"
                " umbral = EXCLUDED.umbral,"
                " decision = EXCLUDED.decision,"
                " motivo = EXCLUDED.motivo,"
                " modelo = EXCLUDED.modelo,"
                " generado_en = CURRENT_TIMESTAMP",
                parametros,
            )
            insertadas += len(lote)
        con.commit()
        cur.close()
    finally:
        con.close()
    return insertadas


def main() -> int:
    parser = argparse.ArgumentParser(description="Registra las decisiones del modelo")
    parser.add_argument(
        "--reemplazar",
        action="store_true",
        help="Borra las decisiones anteriores antes de recalcular",
    )
    args = parser.parse_args()

    red, pre, estado = cargar_modelo()
    if red is None:
        return 1

    umbral = float(estado.get("umbral", 0.5))
    print("=" * 70)
    print(" REGISTRO DE DECISIONES")
    print("=" * 70)
    print(f"Modelo: {estado['tabla']} | umbral {umbral:.2f}")

    tabla = consultar(
        "SELECT r.id_revision, p.codigo_pieza, r.temperatura_c,"
        " r.piezas_en_herramienta,"
        " EXTRACT(HOUR FROM r.fecha_revision)::int AS hora_dia"
        " FROM calidad_piezas.revisiones_piezas r"
        " JOIN calidad_piezas.piezas p ON p.id_pieza = r.id_pieza"
        " ORDER BY r.id_revision"
    )
    if len(tabla) == 0:
        print("No hay revisiones para evaluar.")
        return 1

    X = pre.transformar_nuevos_datos(tabla)
    probabilidades = red.predecir_probabilidad(X).ravel()

    i_revision = tabla.columnas.index("id_revision")
    i_desgaste = tabla.columnas.index("piezas_en_herramienta")

    if args.reemplazar:
        con = obtener_conexion()
        try:
            cur = con.cursor()
            cur.execute("DELETE FROM calidad_piezas.decisiones")
            con.commit()
            cur.close()
        finally:
            con.close()
        print("Decisiones anteriores borradas.")

    filas = []
    conteo: dict[str, int] = {}
    for i in range(len(tabla)):
        probabilidad = float(probabilidades[i])
        desgaste = int(tabla.filas[i][i_desgaste] or 0)
        decision = decidir(probabilidad, umbral)
        conteo[decision] = conteo.get(decision, 0) + 1
        filas.append(
            (
                int(tabla.filas[i][i_revision]),
                round(probabilidad, 4),
                round(umbral, 4),
                decision,
                motivo(decision, probabilidad, umbral, desgaste),
                "modelo_supabase_ia.npz",
            )
        )

    guardadas = guardar(filas)
    print(f"\nPiezas evaluadas: {len(tabla)} | decisiones guardadas: {guardadas}")
    print("\nDistribución de decisiones:")
    for decision, cantidad in sorted(conteo.items(), key=lambda kv: -kv[1]):
        print(f"  {decision:<22}{cantidad:>7}  ({cantidad / len(tabla) * 100:5.2f} %)")
    print("\nConsulta en Power BI: public.v_decisiones")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
