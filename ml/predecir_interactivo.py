"""
Módulo de Inferencia para el modelo entrenado con datos de Supabase
"""

import os
import numpy as np


def cargar_modelo(ruta="modelo_supabase_ia.npz"):
    if not os.path.exists(ruta):
        print(f"Error: No se encontró '{ruta}'. Ejecuta primero 'python entrenar_con_supabase.py'.")
        return None
    return np.load(ruta)


def inferencia(X, pesos):
    relu = lambda z: np.maximum(0, z)
    sigmoide = lambda z: 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))

    Z1 = np.dot(X, pesos["W1"]) + pesos["b1"]
    A1 = relu(Z1)

    Z2 = np.dot(A1, pesos["W2"]) + pesos["b2"]
    A2 = relu(Z2)

    Z3 = np.dot(A2, pesos["W3"]) + pesos["b3"]
    return sigmoide(Z3)


def main():
    modelo = cargar_modelo()
    if modelo is None:
        return

    config = modelo["config"]
    n_entradas = config[0]
    print("\n" + "=" * 50)
    print(" MODELO DE IA ENTRENADO CON DATOS DE SUPABASE")
    print("=" * 50)
    print(f"Número de características de entrada: {n_entradas}")
    print("El modelo está listo para recibir nuevos registros y realizar predicciones.")


if __name__ == "__main__":
    main()
