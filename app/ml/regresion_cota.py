"""Predicción del valor de una cota a partir de las condiciones de máquina.

Ajusta una regresión lineal por mínimos cuadrados:

    valor = b0 + b1 * temperatura + b2 * desgaste

y compara los coeficientes con la física del simulador:

    b1 teórico = 11.5e-6 * nominal     (dilatación del acero)
    b2 teórico = deriva_total_sigmas * sigma / vida_herramienta

Si el modelo recupera esos valores, significa que la regresión encontró la
relación causal real y no una correlación espuria.

Uso:
    python regresion_cota.py --cota cota_plm_c01
    python regresion_cota.py --listar
"""

from __future__ import annotations

import argparse

import numpy as np

from conexion_supabase import cargar_datos_tabla, consultar

CTE_ACERO = 11.5e-6
CICLO_HERRAMIENTA = 300  # debe coincidir con proceso.json


def listar_cotas() -> int:
    tabla = consultar(
        "SELECT codigo_cota, nombre_caracteristica, valor_nominal, tipo_cota"
        " FROM calidad_piezas.cotas_definicion ORDER BY valor_nominal DESC"
    )
    print(f"{'columna':<22}{'nominal':>10}  nombre")
    for codigo, nombre, nominal, tipo in tabla.filas:
        columna = "cota_" + str(codigo).lower().replace("-", "_")
        print(f"{columna:<22}{float(nominal):>10.2f}  {nombre} ({tipo})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Regresión del valor de una cota")
    parser.add_argument("--cota", default="cota_plm_c01", help="Columna de la vista")
    parser.add_argument("--listar", action="store_true", help="Muestra las cotas disponibles")
    args = parser.parse_args()

    if args.listar:
        return listar_cotas()

    print("=" * 70)
    print(" REGRESIÓN DEL VALOR DE UNA COTA")
    print("=" * 70)

    tabla = cargar_datos_tabla("v_entrenamiento_piezas")
    if args.cota not in tabla.columnas:
        print(f"La columna '{args.cota}' no existe. Usa --listar para ver las disponibles.")
        return 1

    i_valor = tabla.columnas.index(args.cota)
    i_temp = tabla.columnas.index("temperatura_c")
    i_desg = tabla.columnas.index("piezas_en_herramienta")
    i_pieza = tabla.columnas.index("codigo_pieza")

    # Solo las filas del componente al que pertenece la cota (el resto son nulos)
    filas = [f for f in tabla.filas if f[i_valor] is not None]
    if len(filas) < 30:
        print(f"Muy pocas muestras para esa cota ({len(filas)}).")
        return 1

    y = np.array([float(f[i_valor]) for f in filas])
    temp = np.array([float(f[i_temp]) for f in filas])
    desgaste = np.array([float(f[i_desg]) for f in filas])
    codigo_pieza = str(filas[0][i_pieza])

    X = np.column_stack([np.ones(len(y)), temp, desgaste])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)

    prediccion = X @ beta
    residuo = y - prediccion
    ss_res = float(np.sum(residuo**2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    mae = float(np.mean(np.abs(residuo)))

    print(f"\nCota        : {args.cota}  (componente {codigo_pieza})")
    print(f"Muestras    : {len(y)}")
    print(f"Rango real  : {y.min():.2f} a {y.max():.2f}")
    print(f"\nEcuación ajustada:")
    print(f"  valor = {beta[0]:.3f} + {beta[1]:.4f} * temperatura + {beta[2]:.5f} * desgaste")
    print(f"\nCalidad del ajuste:")
    print(f"  R²  = {r2:.3f}   (1.0 sería perfecto)")
    print(f"  MAE = {mae:.3f}   (error medio absoluto, en unidades de la cota)")

    # Comparación con la física del simulador
    catalogo = consultar(
        "SELECT valor_nominal, (tolerancia_superior - tolerancia_inferior) / 2"
        " FROM calidad_piezas.cotas_definicion WHERE codigo_cota = %s",
        (args.cota.replace("cota_", "").replace("_", "-").upper(),),
    )
    if catalogo.filas:
        nominal = float(catalogo.filas[0][0])
        semi_banda = float(catalogo.filas[0][1])
        sigma = semi_banda / (3 * 1.33)  # aproximación con Cpk objetivo típico
        teoria_temp = CTE_ACERO * nominal
        teoria_desgaste = 3.0 * sigma / CICLO_HERRAMIENTA

        print(f"\nComparación con la teoría (nominal {nominal:.2f}):")
        print(f"  dilatación   medida {beta[1]:.5f} vs teórica {teoria_temp:.5f} (mm/°C)")
        print(f"  deriva       medida {beta[2]:.5f} vs teórica {teoria_desgaste:.5f} (mm/pieza)")
        print(
            "\n  Nota: la deriva medida suele ser menor que la teórica porque cada cota\n"
            "  tiene su propio factor de desgaste (0.4 a 1.0), y la temperatura está\n"
            "  correlacionada con el desgaste por el calentamiento de la máquina."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
