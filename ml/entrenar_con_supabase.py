"""
=============================================================================
PIPELINE DE MACHINE LEARNING CON BASE DE DATOS SUPABASE
Consume los datos reales de PostgreSQL y entrena la Inteligencia Artificial.
=============================================================================
"""

import os
import sys
import numpy as np
import pandas as pd
from conexion_supabase import (
    listar_tablas_disponibles,
    cargar_datos_tabla,
    inspeccionar_tabla,
)
from red_neuronal_ia import (
    PreprocesadorDatosIA,
    RedNeuronalIA,
    evaluar_metricas,
)


def main():
    print("\n" + "=" * 70)
    print(" INICIANDO MACHINE LEARNING CON DATOS REALES DE SUPABASE")
    print("=" * 70)

    # 1. Obtener lista de tablas de la base de datos
    try:
        tablas = listar_tablas_disponibles()
    except Exception as e:
        print("\n❌ Error al conectar a la base de datos:")
        print(e)
        print("\nRecuerda verificar tu archivo '.env' y colocar tu contraseña en SUPABASE_PASSWORD.")
        sys.exit(1)

    if not tablas:
        print("\n⚠️ No se encontraron tablas en el esquema 'public' de tu base de datos.")
        print("Por favor crea o sube una tabla a Supabase para poder entrenar el modelo.")
        sys.exit(1)

    print(f"\nTablas detectadas en tu base de datos Supabase: {tablas}")

    # 2. Seleccionar la tabla a procesar
    tabla_config = os.getenv("SUPABASE_TABLE", "")
    if tabla_config and tabla_config in tablas:
        tabla_elegida = tabla_config
    else:
        tabla_elegida = tablas[0]

    print(f"\n-> Procesando datos originales de la tabla: '{tabla_elegida}'")

    # 3. Inspeccionar estructura de la tabla
    inspeccionar_tabla(tabla_elegida)

    # 4. Descargar todos los registros de la tabla
    df_real = cargar_datos_tabla(tabla_elegida)

    if len(df_real) < 10:
        print(f"\n⚠️ La tabla '{tabla_elegida}' tiene muy pocos registros ({len(df_real)}).")
        print("Se recomiendan al menos 50 o 100 registros para entrenar el modelo de Machine Learning.")
        if len(df_real) == 0:
            sys.exit(1)

    # 5. Preprocesamiento adaptativo a las columnas reales de la BD
    preprocesador = PreprocesadorDatosIA()
    col_target_config = os.getenv("SUPABASE_TARGET_COLUMN", None)
    X, y = preprocesador.ajustar_y_transformar(df_real, columna_target=col_target_config)

    # 6. División Train (80%) y Test (20%)
    np.random.seed(42)
    indices = np.random.permutation(len(X))
    corte = max(1, int(len(X) * 0.8))

    X_train, y_train = X[indices[:corte]], y[indices[:corte]]
    X_test, y_test = X[indices[corte:]], y[indices[corte:]]

    print(f"Muestras de Entrenamiento: {len(X_train)} | Muestras de Validación: {len(X_test)}")

    # 7. Inicializar y entrenar la Red Neuronal con la dimensionalidad real
    n_features = X.shape[1]
    ia = RedNeuronalIA(
        n_entradas=n_features,
        n_oculta1=min(32, max(8, n_features * 2)),
        n_oculta2=min(16, max(4, n_features)),
        tasa_aprendizaje=0.03
    )

    ia.entrenar(X_train, y_train, epocas=800, verbose_cada=200)

    # 8. Evaluación con datos de prueba
    if len(X_test) > 0:
        y_pred = ia.predecir(X_test)
        evaluar_metricas(y_test, y_pred)

    # 9. Guardar modelo entrenado
    ia.guardar("modelo_supabase_ia.npz")

    # 10. Probar predicción con las primeras filas reales
    print("\n" + "=" * 60)
    print(" DEMOSTRACIÓN: PREDICCIÓN CON LOS PRIMEROS REGISTROS DE LA BD")
    print("=" * 60)
    muestra_real = df_real.head(3)
    X_muestra = preprocesador.transformar_nuevos_datos(muestra_real)
    probs = ia.predecir_probabilidad(X_muestra)
    preds = ia.predecir(X_muestra)

    for i, (_, fila) in enumerate(muestra_real.iterrows()):
        print(f"\nRegistro #{i+1} de la Base de Datos:")
        # Mostrar resumen de valores clave
        valores_resumen = {k: v for k, v in fila.items() if k != preprocesador.columna_target}
        print(f"  Datos: {valores_resumen}")
        if preprocesador.columna_target in fila:
            print(f"  Valor Real ({preprocesador.columna_target}): {fila[preprocesador.columna_target]}")
        print(f"  -> Probabilidad estimada por IA: {probs[i][0] * 100:.2f}%")
        print(f"  -> Predicción del modelo: {preds[i][0]}")

    print("\n" + "=" * 70)
    print(" ¡Entrenamiento completado exitosamente con tus datos de Supabase!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
