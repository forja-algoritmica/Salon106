"""
=============================================================================
SISTEMA DE MACHINE LEARNING E INTELIGENCIA ARTIFICIAL EN PYTHON
Modelo: Red Neuronal Artificial Adaptativa (Multilayer Perceptron / Deep Learning)
Diseñado para consumir y entrenar directamente sobre datos de Base de Datos
=============================================================================

Dependencias: solo numpy. El preprocesamiento trabaja sobre la clase `Tabla`
de `conexion_supabase` en lugar de pandas, para que el pipeline funcione en
equipos donde las extensiones compiladas están bloqueadas por políticas de
seguridad (WDAC) y también dentro del contenedor Linux.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

import numpy as np

from conexion_supabase import Tabla

# Columnas que nunca son predictoras.
COLUMNAS_IGNORADAS = {"id", "uuid", "created_at", "updated_at", "fecha_creacion"}
# Tope de categorías: evita explotar en columnas de alta cardinalidad
# (por ejemplo, números de serie).
MAX_CATEGORIAS = 50


def _a_float(valor):
    """Convierte a float; devuelve None si no es numérico."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float, Decimal)):
        return float(valor)
    try:
        return float(str(valor).strip())
    except (TypeError, ValueError):
        return None


class PreprocesadorDatosIA:
    """Preprocesa cualquier tabla de la base de datos.

    - Imputa nulos (mediana en numéricas, moda en categóricas).
    - Normaliza numéricas con Z-score.
    - Codifica categóricas con One-Hot.
    - Prepara la variable objetivo binaria.
    """

    def __init__(self) -> None:
        self.columnas_numericas: list[str] = []
        self.columnas_categoricas: list[str] = []
        self.medias: dict[str, float] = {}
        self.desviaciones: dict[str, float] = {}
        self.valores_categoricos: dict[str, list[str]] = {}
        self.columnas_finales_x: list[str] = []
        self.columna_target: str | None = None
        self.tipo_target = "binario"
        self.mapa_target: dict[str, float] = {}

    # -- ajuste ------------------------------------------------------------
    def ajustar_y_transformar(self, tabla: Tabla, columna_target: str | None = None):
        if columna_target and columna_target in tabla.columnas:
            self.columna_target = columna_target
        else:
            posibles = [
                "target", "label", "estado", "status", "riesgo",
                "resultado", "class", "categoria", "conforme",
            ]
            coincidencias = [
                c for c in tabla.columnas if c.lower() in posibles
            ]
            self.columna_target = coincidencias[0] if coincidencias else tabla.columnas[-1]

        y_crudo = tabla.columna(self.columna_target)

        features = [
            c
            for c in tabla.columnas
            if c != self.columna_target and c.lower() not in COLUMNAS_IGNORADAS
        ]

        # Clasificar columnas por tipo real de dato
        for columna in features:
            valores = tabla.columna(columna)
            numericos = [_a_float(v) for v in valores]
            no_nulos = [v for v in numericos if v is not None]
            if no_nulos and len(no_nulos) == len([v for v in valores if v is not None]):
                self.columnas_numericas.append(columna)
            else:
                unicos = {str(v) for v in valores if v is not None}
                if len(unicos) > MAX_CATEGORIAS:
                    print(
                        f"  Aviso: se omite '{columna}' "
                        f"({len(unicos)} valores distintos, demasiado para one-hot)"
                    )
                    continue
                self.columnas_categoricas.append(columna)

        # Ajuste de numéricas
        matriz = []
        for columna in self.columnas_numericas:
            numericos = [_a_float(v) for v in tabla.columna(columna)]
            validos = [v for v in numericos if v is not None]
            mediana = float(np.median(validos)) if validos else 0.0
            completos = [v if v is not None else mediana for v in numericos]
            media = float(np.mean(completos)) if completos else 0.0
            std = float(np.std(completos)) if completos else 0.0
            if std == 0:
                std = 1.0
            self.medias[columna] = media
            self.desviaciones[columna] = std

        # Ajuste de categóricas
        columnas_dummy: list[tuple[str, list[str]]] = []
        for columna in self.columnas_categoricas:
            valores = [str(v) if v is not None else None for v in tabla.columna(columna)]
            conteo = Counter(v for v in valores if v is not None)
            moda = conteo.most_common(1)[0][0] if conteo else "DESCONOCIDO"
            completos = [v if v is not None else moda for v in valores]
            unicos = sorted(set(completos))
            self.valores_categoricos[columna] = unicos
            columnas_dummy.append((columna, unicos))

        # Construcción de la matriz X
        self.columnas_finales_x = list(self.columnas_numericas)
        for columna, unicos in columnas_dummy:
            self.columnas_finales_x.extend(f"{columna}_{v}" for v in unicos)

        for i in range(len(tabla)):
            fila = []
            for columna in self.columnas_numericas:
                valor = _a_float(tabla.filas[i][tabla.columnas.index(columna)])
                if valor is None:
                    valor = self.medias[columna]
                fila.append((valor - self.medias[columna]) / self.desviaciones[columna])
            for columna, unicos in columnas_dummy:
                valor = tabla.filas[i][tabla.columnas.index(columna)]
                texto = str(valor) if valor is not None else None
                if texto is None:
                    conteo = Counter(
                        str(v) for v in tabla.columna(columna) if v is not None
                    )
                    texto = conteo.most_common(1)[0][0] if conteo else "DESCONOCIDO"
                fila.extend(1.0 if texto == v else 0.0 for v in unicos)
            matriz.append(fila)

        X = np.array(matriz, dtype=np.float64)

        # Variable objetivo
        y_limpio = [v for v in y_crudo]
        numericos_y = [_a_float(v) for v in y_limpio]
        if all(v is not None for v in numericos_y):
            y_proc = np.array(numericos_y, dtype=np.float64)
        else:
            valores_target = sorted({str(v) for v in y_limpio if v is not None})
            self.mapa_target = {v: float(i) for i, v in enumerate(valores_target)}
            y_proc = np.array(
                [self.mapa_target.get(str(v), 0.0) for v in y_limpio], dtype=np.float64
            )

        unicos = np.unique(y_proc)
        if len(unicos) <= 2:
            self.tipo_target = "binario"
            y_proc = (y_proc == unicos[-1]).astype(np.float64)
        else:
            self.tipo_target = "continuo"
        y = y_proc.reshape(-1, 1)

        print("\n" + "=" * 60)
        print(" RESUMEN DEL PREPROCESAMIENTO")
        print("=" * 60)
        print(f"• Registros procesados: {len(X)}")
        print(f"• Objetivo: '{self.columna_target}' ({self.tipo_target})")
        print(f"• Numéricas: {len(self.columnas_numericas)}")
        print(f"• Categóricas: {len(self.columnas_categoricas)}")
        print(f"• Entradas resultantes: {len(self.columnas_finales_x)}")
        print("=" * 60)

        return X, y

    # -- inferencia --------------------------------------------------------
    def transformar_nuevos_datos(self, tabla: Tabla) -> np.ndarray:
        """Aplica el mismo preprocesamiento a datos nuevos."""
        matriz = []
        for i in range(len(tabla)):
            fila = []
            for columna in self.columnas_numericas:
                if columna in tabla.columnas:
                    valor = _a_float(tabla.filas[i][tabla.columnas.index(columna)])
                else:
                    valor = None
                if valor is None:
                    valor = self.medias.get(columna, 0.0)
                fila.append((valor - self.medias[columna]) / self.desviaciones[columna])
            for columna in self.columnas_categoricas:
                valor = (
                    tabla.filas[i][tabla.columnas.index(columna)]
                    if columna in tabla.columnas
                    else None
                )
                texto = str(valor) if valor is not None else ""
                fila.extend(
                    1.0 if texto == v else 0.0
                    for v in self.valores_categoricos.get(columna, [])
                )
            matriz.append(fila)
        return np.array(matriz, dtype=np.float64)

    # -- persistencia ------------------------------------------------------
    def exportar_estado(self) -> dict:
        return {
            "columnas_numericas": self.columnas_numericas,
            "columnas_categoricas": self.columnas_categoricas,
            "medias": self.medias,
            "desviaciones": self.desviaciones,
            "valores_categoricos": self.valores_categoricos,
            "columnas_finales_x": self.columnas_finales_x,
            "columna_target": self.columna_target,
            "tipo_target": self.tipo_target,
            "mapa_target": self.mapa_target,
        }

    @classmethod
    def desde_estado(cls, datos: dict) -> "PreprocesadorDatosIA":
        pre = cls()
        pre.columnas_numericas = datos["columnas_numericas"]
        pre.columnas_categoricas = datos["columnas_categoricas"]
        pre.medias = datos["medias"]
        pre.desviaciones = datos["desviaciones"]
        pre.valores_categoricos = datos["valores_categoricos"]
        pre.columnas_finales_x = datos["columnas_finales_x"]
        pre.columna_target = datos.get("columna_target")
        pre.tipo_target = datos.get("tipo_target", "binario")
        pre.mapa_target = datos.get("mapa_target", {})
        return pre


# =====================================================================
# RED NEURONAL PROFUNDA DINÁMICA (ADAPTATIVA A CUALQUIER TABLA)
# =====================================================================
class RedNeuronalIA:
    """Red Neuronal Multicapa configurable.

    Entrada: n_entradas (según las columnas de la BD)
    Capa Oculta 1: ReLU
    Capa Oculta 2: ReLU
    Capa Salida: 1 neurona con Sigmoide (clasificación binaria)
    """

    def __init__(
        self,
        n_entradas: int,
        n_oculta1: int = 16,
        n_oculta2: int = 8,
        tasa_aprendizaje: float = 0.05,
    ):
        self.n_entradas = n_entradas
        self.n_oculta1 = n_oculta1
        self.n_oculta2 = n_oculta2
        self.lr = tasa_aprendizaje

        rng = np.random.default_rng(42)  # inicialización de He
        self.W1 = rng.standard_normal((n_entradas, n_oculta1)) * np.sqrt(2.0 / n_entradas)
        self.b1 = np.zeros((1, n_oculta1))
        self.W2 = rng.standard_normal((n_oculta1, n_oculta2)) * np.sqrt(2.0 / n_oculta1)
        self.b2 = np.zeros((1, n_oculta2))
        self.W3 = rng.standard_normal((n_oculta2, 1)) * np.sqrt(2.0 / n_oculta2)
        self.b3 = np.zeros((1, 1))

    @staticmethod
    def relu(z):
        return np.maximum(0, z)

    @staticmethod
    def derivada_relu(z):
        return (z > 0).astype(float)

    @staticmethod
    def sigmoide(z):
        return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))

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
        y_pred = np.clip(y_pred, 1e-15, 1 - 1e-15)
        return -(1 / m) * np.sum(
            y_real * np.log(y_pred) + (1 - y_real) * np.log(1 - y_pred)
        )

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
        print(f"\nEntrenando con {len(X)} muestras ({epocas} épocas) ...")
        print("-" * 65)
        for epoca in range(1, epocas + 1):
            pred = self.forward(X)
            perdida = self.calcular_perdida(y, pred)
            acierto = np.mean((pred >= 0.5).astype(int) == y) * 100
            self.backward(X, y)
            if epoca % verbose_cada == 0 or epoca == 1:
                print(
                    f"Época {epoca:4d}/{epocas} | Pérdida: {perdida:.4f} | "
                    f"Precisión: {acierto:.2f}%"
                )
        print("-" * 65)
        print("Entrenamiento finalizado.\n")

    def predecir_probabilidad(self, X):
        return self.forward(X)

    def predecir(self, X, umbral: float = 0.5):
        return (self.predecir_probabilidad(X) >= umbral).astype(int)

    def guardar(self, ruta: str = "modelo_supabase_ia.npz") -> None:
        np.savez(
            ruta,
            W1=self.W1, b1=self.b1,
            W2=self.W2, b2=self.b2,
            W3=self.W3, b3=self.b3,
            config=np.array([self.n_entradas, self.n_oculta1, self.n_oculta2]),
        )
        print(f"Modelo guardado en: {ruta}")

    @classmethod
    def cargar(cls, ruta: str = "modelo_supabase_ia.npz") -> "RedNeuronalIA":
        datos = np.load(ruta)
        n_entradas, n_oculta1, n_oculta2 = (int(v) for v in datos["config"])
        red = cls(n_entradas, n_oculta1, n_oculta2)
        red.W1, red.b1 = datos["W1"], datos["b1"]
        red.W2, red.b2 = datos["W2"], datos["b2"]
        red.W3, red.b3 = datos["W3"], datos["b3"]
        return red


def evaluar_metricas(y_real, y_pred):
    total = len(y_real)
    vp = int(np.sum((y_real == 1) & (y_pred == 1)))
    vn = int(np.sum((y_real == 0) & (y_pred == 0)))
    fp = int(np.sum((y_real == 0) & (y_pred == 1)))
    fn = int(np.sum((y_real == 1) & (y_pred == 0)))

    acierto = (vp + vn) / total * 100 if total else 0
    precision = vp / (vp + fp) * 100 if (vp + fp) else 0
    recall = vp / (vp + fn) * 100 if (vp + fn) else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0

    print("=" * 55)
    print("      REPORTE DE EVALUACIÓN (DATOS DE LA BD)      ")
    print("=" * 55)
    print(f"Muestras de prueba           : {total}")
    print(f"Exactitud general (Accuracy) : {acierto:.2f}%")
    print(f"Precisión (Precision)        : {precision:.2f}%")
    print(f"Sensibilidad (Recall)        : {recall:.2f}%")
    print(f"Puntaje F1 (F1-Score)        : {f1:.2f}%")
    print("-" * 55)
    print("Matriz de Confusión:")
    print(f"  [VN: {vn:4d}]  [FP: {fp:4d}]")
    print(f"  [FN: {fn:4d}]  [VP: {vp:4d}]")
    print("=" * 55)
    print(
        "Lectura: 'Recall' es qué porcentaje de las piezas malas se detectan.\n"
        "         'Precision' es qué porcentaje de las alarmas son reales."
    )
