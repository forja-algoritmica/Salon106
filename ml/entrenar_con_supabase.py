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


def seleccionar_columna_target(df, target_config):
    """Respeta el objetivo configurado; si no hay uno, aplica la selección automática actual."""
    if target_config:
        if target_config not in df.columns:
            raise ValueError(
                f"La columna indicada en SUPABASE_TARGET_COLUMN "
                f"('{target_config}') no existe. Columnas disponibles: {list(df.columns)}"
            )
        return target_config

    posibles = [
        "target", "label", "estado", "status",
        "riesgo", "resultado", "class", "categoria",
    ]
    coincidencias = [
        columna for columna in df.columns
        if columna.lower() in posibles
    ]

    return coincidencias[0] if coincidencias else df.columns[-1]


def dividir_estratificado(df, columna_target, test_size=0.2, random_state=42):
    """Divide los datos procurando conservar ambas clases en entrenamiento y prueba."""
    if not 0 < test_size < 1:
        raise ValueError("test_size debe ser un número entre 0 y 1.")

    datos = df.reset_index(drop=True)
    rng = np.random.default_rng(random_state)

    indices_train = []
    indices_test = []

    grupos = datos.groupby(columna_target, sort=False).indices

    for clase, posiciones in grupos.items():
        posiciones = np.asarray(posiciones)

        if len(posiciones) < 2:
            raise ValueError(
                f"La clase '{clase}' tiene menos de 2 registros. "
                "No se puede incluirla en entrenamiento y prueba."
            )

        rng.shuffle(posiciones)

        cantidad_test = max(1, int(round(len(posiciones) * test_size)))
        cantidad_test = min(cantidad_test, len(posiciones) - 1)

        indices_test.extend(posiciones[:cantidad_test])
        indices_train.extend(posiciones[cantidad_test:])

    indices_train = np.asarray(indices_train, dtype=int)
    indices_test = np.asarray(indices_test, dtype=int)

    rng.shuffle(indices_train)
    rng.shuffle(indices_test)

    return (
        datos.iloc[indices_train].copy(),
        datos.iloc[indices_test].copy(),
    )


def codificar_target_prueba(df_train, df_test, columna_target):
    """Codifica el objetivo de prueba con la misma regla que usa el preprocesador."""
    clases_train = sorted(df_train[columna_target].dropna().unique())

    if len(clases_train) != 2:
        raise ValueError(
            f"Se encontraron {len(clases_train)} clases en "
            f"'{columna_target}'. RedNeuronalIA actualmente requiere "
            "exactamente 2 clases."
        )

    target_train = df_train[columna_target]

    if np.issubdtype(target_train.dtype, np.number):
        clase_positiva = clases_train[-1]
        y_test = (
            df_test[columna_target].to_numpy() == clase_positiva
        ).astype(np.float64)
    else:
        mapa = {valor: indice for indice, valor in enumerate(clases_train)}
        valores_codificados = (
            df_test[columna_target]
            .map(mapa)
            .fillna(0)
            .to_numpy(dtype=np.float64)
        )
        clase_positiva_codificada = max(mapa.values())
        y_test = (
            valores_codificados == clase_positiva_codificada
        ).astype(np.float64)

    return y_test.reshape(-1, 1)


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
        print(
            "\nVerifica el archivo '.env' y la variable "
            "SUPABASE_PASSWORD."
        )
        sys.exit(1)

    if not tablas:
        print("\n⚠️ No se encontraron tablas en el esquema 'public' de Supabase.")
        print("Crea o sube una tabla antes de entrenar el modelo.")
        sys.exit(1)

    print(f"\nTablas detectadas en Supabase: {tablas}")

    # 2. Seleccionar tabla
    tabla_config = os.getenv("SUPABASE_TABLE", "").strip()

    if tabla_config:
        if tabla_config not in tablas:
            raise ValueError(
                f"La tabla configurada en SUPABASE_TABLE ('{tabla_config}') "
                f"no existe. Tablas disponibles: {tablas}"
            )
        tabla_elegida = tabla_config
    else:
        tabla_elegida = tablas[0]

    print(f"\n-> Procesando la tabla: '{tabla_elegida}'")

    # 3. Inspeccionar estructura y 4. cargar registros
    inspeccionar_tabla(tabla_elegida)
    df_real = cargar_datos_tabla(tabla_elegida)

    if df_real.empty:
        print(f"\n⚠️ La tabla '{tabla_elegida}' no contiene registros.")
        sys.exit(1)

    if len(df_real) < 10:
        print(
            f"\n⚠️ La tabla tiene pocos registros ({len(df_real)}). "
            "Se recomiendan al menos 50 o 100."
        )

    # 5. Identificar objetivo y descartar filas sin etiqueta
    target_config = os.getenv("SUPABASE_TARGET_COLUMN", "").strip()
    columna_target = seleccionar_columna_target(df_real, target_config)

    df_real = df_real.dropna(subset=[columna_target]).copy()

    if df_real.empty:
        raise ValueError(
            f"No quedan registros con un valor válido en '{columna_target}'."
        )

    clases = df_real[columna_target].dropna().unique()
    if len(clases) != 2:
        raise ValueError(
            f"El objetivo '{columna_target}' tiene {len(clases)} clases. "
            "La red actual requiere exactamente 2."
        )

    # 6. Separar antes de ajustar el preprocesador para evitar fuga de datos
    df_train, df_test = dividir_estratificado(
        df_real,
        columna_target=columna_target,
        test_size=0.2,
        random_state=42,
    )

    print(
        f"\nMuestras de entrenamiento: {len(df_train)}"
        f" | Muestras de prueba: {len(df_test)}"
    )

    # 7. Ajustar el preprocesador solo con entrenamiento
    preprocesador = PreprocesadorDatosIA()

    X_train, y_train = preprocesador.ajustar_y_transformar(
        df_train,
        columna_target=columna_target,
    )

    # Aplicar al conjunto de prueba el preprocesamiento aprendido en entrenamiento
    X_test = preprocesador.transformar_nuevos_datos(df_test)
    y_test = codificar_target_prueba(
        df_train,
        df_test,
        columna_target,
    )

    if X_train.shape[1] == 0:
        raise ValueError("No hay características para entrenar el modelo.")

    # 8. Inicializar y entrenar la red neuronal
    n_features = X_train.shape[1]

    ia = RedNeuronalIA(
        n_entradas=n_features,
        n_oculta1=min(32, max(8, n_features * 2)),
        n_oculta2=min(16, max(4, n_features)),
        tasa_aprendizaje=0.03,
    )

    ia.entrenar(
        X_train,
        y_train,
        epocas=800,
        verbose_cada=200,
    )

    # 9. Evaluar con registros separados que no participaron en el ajuste
    y_pred = ia.predecir(X_test)
    evaluar_metricas(y_test, y_pred)

    # 10. Guardar modelo entrenado
    ia.guardar("modelo_supabase_ia.npz")

    # 11. Demostrar predicciones con filas del conjunto de prueba
    print("\n" + "=" * 60)
    print(" DEMOSTRACIÓN: PREDICCIÓN CON REGISTROS DE PRUEBA")
    print("=" * 60)

    muestra_real = df_test.head(3)
    X_muestra = preprocesador.transformar_nuevos_datos(muestra_real)
    probs = ia.predecir_probabilidad(X_muestra)
    preds = ia.predecir(X_muestra)

    for i, (_, fila) in enumerate(muestra_real.iterrows()):
        print(f"\nRegistro de prueba #{i + 1}:")

        valores_resumen = {
            k: v for k, v in fila.items()
            if k != preprocesador.columna_target
        }
        print(f"  Datos: {valores_resumen}")
        print(
            f"  Valor real ({preprocesador.columna_target}): "
            f"{fila[preprocesador.columna_target]}"
        )
        print(f"  -> Probabilidad estimada: {probs[i][0] * 100:.2f}%")
        print(f"  -> Predicción del modelo: {preds[i][0]}")

    print("\n" + "=" * 70)
    print(" ¡Entrenamiento completado exitosamente!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()