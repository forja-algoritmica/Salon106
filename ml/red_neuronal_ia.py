"""
=============================================================================
SISTEMA DE MACHINE LEARNING E INTELIGENCIA ARTIFICIAL EN PYTHON
Modelo: Red Neuronal Artificial Adaptativa (Multilayer Perceptron / Deep Learning)
Diseñado para consumir y entrenar directamente sobre datos de Base de Datos (Supabase)
=============================================================================
"""

import json
import numpy as np
import pandas as pd


class PreprocesadorDatosIA:
    """
    Preprocesa dinámicamente cualquier tabla proveniente de la base de datos:
    - Limpieza de valores nulos.
    - Codificación de variables categóricas (One-Hot / Categorical).
    - Normalización / Estandarización de variables numéricas (Z-score).
    - Detección y preparación de variable objetivo (Target).
    """

    def __init__(self):
        self.columnas_numericas = []
        self.columnas_categoricas = []
        self.medias = {}
        self.desviaciones = {}
        self.valores_categoricos = {}
        self.columnas_finales_x = []
        self.columna_target = None
        self.tipo_target = "binario"  # binario o continuo

    def ajustar_y_transformar(self, df: pd.DataFrame, columna_target: str = None):
        """Ajusta el preprocesador al DataFrame de la BD y retorna matrices X e y listas para la IA."""
        df_limpio = df.copy()

        # Determinar columna objetivo si no fue especificada
        if columna_target and columna_target in df_limpio.columns:
            self.columna_target = columna_target
        else:
            # Buscar nombres típicos de target o usar la última columna
            posibles = ["target", "label", "estado", "status", "riesgo", "resultado", "class", "categoria"]
            coincidencias = [c for c in df_limpio.columns if c.lower() in posibles]
            self.columna_target = coincidencias[0] if coincidencias else df_limpio.columns[-1]

        # Separar objetivo y características
        y_serie = df_limpio[self.columna_target]
        df_caracteristicas = df_limpio.drop(columns=[self.columna_target])

        # Excluir posibles columnas de IDs automáticos (como 'id', 'uuid', etc.)
        columnas_a_ignorar = [c for c in df_caracteristicas.columns if c.lower() in ["id", "uuid", "created_at", "updated_at", "fecha_creacion"]]
        if columnas_a_ignorar:
            print(f"ℹ️ Omitiendo identificadores/fechas no predictivas: {columnas_a_ignorar}")
            df_caracteristicas = df_caracteristicas.drop(columns=columnas_a_ignorar)

        # Detectar columnas numéricas y categóricas
        self.columnas_numericas = df_caracteristicas.select_dtypes(include=[np.number]).columns.tolist()
        self.columnas_categoricas = [c for c in df_caracteristicas.columns if c not in self.columnas_numericas]

        # 1. Tratar y normalizar numéricas
        df_proc = pd.DataFrame(index=df_limpio.index)
        for col in self.columnas_numericas:
            mediana = df_caracteristicas[col].median()
            df_caracteristicas[col] = df_caracteristicas[col].fillna(mediana)
            media = df_caracteristicas[col].mean()
            std = df_caracteristicas[col].std()
            if std == 0 or np.isnan(std):
                std = 1.0

            self.medias[col] = media
            self.desviaciones[col] = std
            df_proc[col] = (df_caracteristicas[col] - media) / std

        # 2. Tratar categóricas con One-Hot Encoding
        for col in self.columnas_categoricas:
            moda = df_caracteristicas[col].mode()[0] if not df_caracteristicas[col].mode().empty else "DESCONOCIDO"
            serie_col = df_caracteristicas[col].fillna(moda).astype(str)
            valores_unicos = sorted(serie_col.unique())
            self.valores_categoricos[col] = valores_unicos

            for val in valores_unicos:
                nombre_dummy = f"{col}_{val}"
                df_proc[nombre_dummy] = (serie_col == val).astype(float)

        self.columnas_finales_x = df_proc.columns.tolist()
        X = df_proc.values.astype(np.float64)

        # 3. Procesar variable objetivo (y)
        # Convertir a binario o numérico si es categórica
        if not np.issubdtype(y_serie.dtype, np.number):
            valores_target = sorted(y_serie.dropna().unique())
            mapa_target = {v: idx for idx, v in enumerate(valores_target)}
            print(f"ℹ️ Mapeo de la variable objetivo '{self.columna_target}': {mapa_target}")
            y_proc = y_serie.map(mapa_target).fillna(0).values.astype(np.float64)
        else:
            y_proc = y_serie.fillna(y_serie.median()).values.astype(np.float64)

        # Si los valores son binarios (0 y 1 o etiquetas discretas)
        unicos = np.unique(y_proc)
        if len(unicos) <= 2:
            self.tipo_target = "binario"
            y_proc = (y_proc == unicos[-1]).astype(np.float64)
        else:
            self.tipo_target = "continuo"

        y = y_proc.reshape(-1, 1)

        print("\n" + "=" * 60)
        print(" RESUMEN DEL PREPROCESAMIENTO DE DATOS DE LA BD")
        print("=" * 60)
        print(f"• Registros totales procesados: {len(X)}")
        print(f"• Variable Objetivo seleccionada: '{self.columna_target}' (Tipo: {self.tipo_target})")
        print(f"• Características de entrada resultantes ({len(self.columnas_finales_x)}):")
        print(f"  {self.columnas_finales_x}")
        print("=" * 60)

        return X, y

    def transformar_nuevos_datos(self, df: pd.DataFrame):
        """Aplica el mismo preprocesamiento a nuevos datos que ingresen para inferencia."""
        df_proc = pd.DataFrame(index=df.index)

        for col in self.columnas_numericas:
            val = df[col] if col in df.columns else self.medias.get(col, 0)
            media = self.medias.get(col, 0)
            std = self.desviaciones.get(col, 1)
            df_proc[col] = (val - media) / std

        for col in self.columnas_categoricas:
            valores_guardados = self.valores_categoricos.get(col, [])
            val = df[col].astype(str) if col in df.columns else ""
            for v in valores_guardados:
                nombre_dummy = f"{col}_{v}"
                df_proc[nombre_dummy] = (val == v).astype(float)

        # Asegurar todas las columnas finales esperadas
        for col_f in self.columnas_finales_x:
            if col_f not in df_proc.columns:
                df_proc[col_f] = 0.0

        return df_proc[self.columnas_finales_x].values.astype(np.float64)


# =====================================================================
# RED NEURONAL PROFUNDA DINÁMICA (ADAPTATIVA A CUALQUIER TABLA)
# =====================================================================
class RedNeuronalIA:
    """
    Red Neuronal Multicapa configurable:
    Entrada: n_entradas (adaptado a las columnas de la BD)
    Capa Oculta 1: n_oculta1 neuronas con activación ReLU
    Capa Oculta 2: n_oculta2 neuronas con activación ReLU
    Capa Salida: 1 neurona (Sigmoide si binario)
    """

    def __init__(self, n_entradas: int, n_oculta1: int = 16, n_oculta2: int = 8, tasa_aprendizaje: float = 0.05):
        self.n_entradas = n_entradas
        self.n_oculta1 = n_oculta1
        self.n_oculta2 = n_oculta2
        self.lr = tasa_aprendizaje

        # Inicialización de He
        np.random.seed(42)
        self.W1 = np.random.randn(n_entradas, n_oculta1) * np.sqrt(2.0 / n_entradas)
        self.b1 = np.zeros((1, n_oculta1))

        self.W2 = np.random.randn(n_oculta1, n_oculta2) * np.sqrt(2.0 / n_oculta1)
        self.b2 = np.zeros((1, n_oculta2))

        self.W3 = np.random.randn(n_oculta2, 1) * np.sqrt(2.0 / n_oculta2)
        self.b3 = np.zeros((1, 1))

    @staticmethod
    def relu(z):
        return np.maximum(0, z)

    @staticmethod
    def derivada_relu(z):
        return (z > 0).astype(float)

    @staticmethod
    def sigmoide(z):
        z_clip = np.clip(z, -500, 500)
        return 1.0 / (1.0 + np.exp(-z_clip))

    def forward(self, X):
        self.Z1 = np.dot(X, self.W1) + self.b1
        self.A1 = self.relu(self.Z1)

        self.Z2 = np.dot(self.A1, self.W2) + self.b2
        self.A2 = self.relu(self.Z2)

        self.Z3 = np.dot(self.A2, self.W3) + self.b3
        self.A3 = self.sigmoide(self.Z3)
        return self.A3

    @staticmethod
    def calcular_perdida(y_real, y_pred):
        m = y_real.shape[0]
        epsilon = 1e-15
        y_pred = np.clip(y_pred, epsilon, 1 - epsilon)
        return - (1 / m) * np.sum(y_real * np.log(y_pred) + (1 - y_real) * np.log(1 - y_pred))

    def backward(self, X, y):
        m = X.shape[0]

        dZ3 = self.A3 - y
        dW3 = (1 / m) * np.dot(self.A2.T, dZ3)
        db3 = (1 / m) * np.sum(dZ3, axis=0, keepdims=True)

        dA2 = np.dot(dZ3, self.W3.T)
        dZ2 = dA2 * self.derivada_relu(self.Z2)
        dW2 = (1 / m) * np.dot(self.A1.T, dZ2)
        db2 = (1 / m) * np.sum(dZ2, axis=0, keepdims=True)

        dA1 = np.dot(dZ2, self.W2.T)
        dZ1 = dA1 * self.derivada_relu(self.Z1)
        dW1 = (1 / m) * np.dot(X.T, dZ1)
        db1 = (1 / m) * np.sum(dZ1, axis=0, keepdims=True)

        self.W3 -= self.lr * dW3
        self.b3 -= self.lr * db3
        self.W2 -= self.lr * dW2
        self.b2 -= self.lr * db2
        self.W1 -= self.lr * dW1
        self.b1 -= self.lr * db1

    def entrenar(self, X, y, epocas: int = 1000, verbose_cada: int = 200):
        print(f"\nIniciando entrenamiento del modelo con datos de la BD ({epocas} épocas)...")
        print("-" * 65)

        for epoca in range(1, epocas + 1):
            pred = self.forward(X)
            loss = self.calcular_perdida(y, pred)
            clases = (pred >= 0.5).astype(int)
            acc = np.mean(clases == y) * 100

            self.backward(X, y)

            if epoca % verbose_cada == 0 or epoca == 1:
                print(f"Época {epoca:4d}/{epocas} | Pérdida (Loss): {loss:.4f} | Precisión: {acc:.2f}%")

        print("-" * 65)
        print("¡Entrenamiento finalizado exitosamente!\n")

    def predecir_probabilidad(self, X):
        return self.forward(X)

    def predecir(self, X, umbral: float = 0.5):
        return (self.predecir_probabilidad(X) >= umbral).astype(int)

    def guardar(self, ruta="modelo_supabase_ia.npz"):
        np.savez(
            ruta,
            W1=self.W1, b1=self.b1,
            W2=self.W2, b2=self.b2,
            W3=self.W3, b3=self.b3,
            config=np.array([self.n_entradas, self.n_oculta1, self.n_oculta2])
        )
        print(f"Modelo de IA guardado en: {ruta}")


def evaluar_metricas(y_real, y_pred):
    total = len(y_real)
    vp = np.sum((y_real == 1) & (y_pred == 1))
    vn = np.sum((y_real == 0) & (y_pred == 0))
    fp = np.sum((y_real == 0) & (y_pred == 1))
    fn = np.sum((y_real == 1) & (y_pred == 0))

    acc = (vp + vn) / total * 100 if total > 0 else 0
    precision = vp / (vp + fp) * 100 if (vp + fp) > 0 else 0
    recall = vp / (vp + fn) * 100 if (vp + fn) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

    print("=" * 55)
    print("      REPORTE DE EVALUACIÓN (DATOS REALES DE LA BD)      ")
    print("=" * 55)
    print(f"Muestras de prueba evaluadas : {total}")
    print(f"Exactitud general (Accuracy) : {acc:.2f}%")
    print(f"Precisión (Precision)        : {precision:.2f}%")
    print(f"Sensibilidad (Recall)        : {recall:.2f}%")
    print(f"Puntaje F1 (F1-Score)        : {f1:.2f}%")
    print("-" * 55)
    print(f"Matriz de Confusión:")
    print(f"  [VN: {vn:4d}]  [FP: {fp:4d}]")
    print(f"  [FN: {fn:4d}]  [VP: {vp:4d}]")
    print("=" * 55)
