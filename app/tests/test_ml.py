"""Pruebas del pipeline de machine learning (servicio `ml`), sin tocar la BD."""

from __future__ import annotations

import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
for _sub in ("app", "ml"):
    _r = str(_RAIZ / _sub)
    if _r not in sys.path:
        sys.path.insert(0, _r)

import numpy as np

try:
    import pytest
except ImportError:
    class _Approx:
        def __init__(self, v, abs=None):
            self.v = v
            self.abs = abs or 1e-4

        def __eq__(self, other):
            return abs(self.v - other) <= self.abs

    class pytest:  # type: ignore
        approx = _Approx

from conexion_supabase import Tabla
from detectar_anomalias import ajustar, puntajes
from entrenar_con_supabase import dividir_tres, elegir_umbral, sobremuestrear
from predecir_interactivo import decidir
from red_neuronal_ia import PreprocesadorDatosIA, RedNeuronalIA


# ---------------------------------------------------------------------------
# Preprocesamiento
# ---------------------------------------------------------------------------
def _tabla_ejemplo() -> Tabla:
    filas = []
    for i in range(40):
        filas.append((float(i), 20.0 + i * 0.1, "OK" if i % 2 == 0 else "NOK", 0.0))
    return Tabla(columnas=["medida", "temperatura", "estado", "conforme"], filas=filas)


def test_el_preprocesador_separa_numericas_y_categoricas():
    pre = PreprocesadorDatosIA()
    X, y = pre.ajustar_y_transformar(_tabla_ejemplo(), columna_target="conforme")

    assert X.shape[0] == 40
    assert "medida" in pre.columnas_numericas
    assert "estado" in pre.columnas_categoricas
    assert y.shape == (40, 1)
    # El estado tiene 2 valores -> 2 columnas dummy
    assert len(pre.columnas_finales_x) == 2 + 2


def test_el_preprocesamiento_es_reutilizable():
    pre = PreprocesadorDatosIA()
    pre.ajustar_y_transformar(_tabla_ejemplo(), columna_target="conforme")

    guardado = pre.exportar_estado()
    recuperado = PreprocesadorDatosIA.desde_estado(guardado)

    X_nuevo = recuperado.transformar_nuevos_datos(_tabla_ejemplo())
    assert X_nuevo.shape[1] == len(pre.columnas_finales_x)


def test_las_columnas_de_alta_cardinalidad_se_descartan():
    filas = [(f"SERIE-{i}", float(i), 0.0) for i in range(120)]
    tabla = Tabla(columnas=["serie", "valor", "conforme"], filas=filas)
    pre = PreprocesadorDatosIA()
    pre.ajustar_y_transformar(tabla, columna_target="conforme")
    assert "serie" not in pre.columnas_categoricas


# ---------------------------------------------------------------------------
# Red neuronal
# ---------------------------------------------------------------------------
def test_la_red_produce_una_salida_por_muestra():
    red = RedNeuronalIA(n_entradas=5, n_oculta1=4, n_oculta2=3)
    X = np.random.default_rng(0).normal(size=(12, 5))
    salida = red.forward(X)
    assert salida.shape == (12, 1)
    assert np.all((salida >= 0) & (salida <= 1))


def test_la_red_aprende_una_funcion_simple():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(300, 3))
    y = (X[:, 0] + X[:, 1] > 0).astype(float).reshape(-1, 1)

    red = RedNeuronalIA(n_entradas=3, n_oculta1=8, n_oculta2=4, tasa_aprendizaje=0.1)
    red.entrenar(X, y, epocas=300, verbose_cada=300)

    acierto = float(np.mean(red.predecir(X) == y) * 100)
    assert acierto > 85


# ---------------------------------------------------------------------------
# División, desbalance y umbral
# ---------------------------------------------------------------------------
def test_la_division_conserva_ambas_clases():
    y = np.array([0] * 100 + [1] * 20).reshape(-1, 1)
    idx_train, idx_val, idx_test = dividir_tres(y)

    for indices in (idx_train, idx_val, idx_test):
        assert set(np.unique(y[indices])) == {0.0, 1.0}


def test_el_sobremuestreo_equilibra_las_clases():
    X = np.arange(120, dtype=float).reshape(-1, 1)
    y = np.array([0] * 100 + [1] * 20, dtype=float).reshape(-1, 1)
    X_bal, y_bal = sobremuestrear(X, y)

    assert len(X_bal) == len(y_bal)
    assert abs(y_bal.sum() - (len(y_bal) - y_bal.sum())) <= 1


def test_el_umbral_elegido_es_razonable():
    prob = np.array([0.05, 0.1, 0.2, 0.85, 0.9, 0.95])
    y = np.array([0, 0, 0, 1, 1, 1], dtype=float).reshape(-1, 1)
    umbral, precision, recall = elegir_umbral(prob, y)

    assert 0.3 <= umbral <= 0.95
    assert precision == 100.0
    assert recall == 100.0


# ---------------------------------------------------------------------------
# Decisiones operativas
# ---------------------------------------------------------------------------
def test_las_decisiones_respetan_los_umbrales():
    umbral = 0.7
    assert decidir(0.10, umbral) == "CONTINUAR"
    assert decidir(0.70, umbral) == "REVISAR PIEZA"
    assert decidir(0.90, umbral) == "CAMBIAR HERRAMIENTA"


# ---------------------------------------------------------------------------
# Anomalías
# ---------------------------------------------------------------------------
def test_una_pieza_extrema_es_la_mas_anomala():
    rng = np.random.default_rng(3)
    normales = rng.normal(0, 1, size=(200, 4))
    extrema = np.array([[9.0, 9.0, 9.0, 9.0]])
    X = np.vstack([normales, extrema])

    media, desviacion = ajustar(X, np.ones(len(X), dtype=bool))
    max_z, _ = puntajes(X, media, desviacion)

    assert int(np.argmax(max_z)) == len(X) - 1


# ---------------------------------------------------------------------------
# Regresión de una cota
# ---------------------------------------------------------------------------
def test_la_regresion_recupera_los_coeficientes():
    rng = np.random.default_rng(4)
    temperatura = rng.uniform(18, 26, 400)
    desgaste = rng.uniform(0, 300, 400)
    y = 100.0 + 0.05 * temperatura + 0.002 * desgaste + rng.normal(0, 0.01, 400)

    X = np.column_stack([np.ones(len(y)), temperatura, desgaste])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)

    assert beta[0] == pytest.approx(100.0, abs=0.5)
    assert beta[1] == pytest.approx(0.05, abs=0.002)
    assert beta[2] == pytest.approx(0.002, abs=0.0001)


# ---------------------------------------------------------------------------
# Análisis detallado con IA y Recomendaciones
# ---------------------------------------------------------------------------
def test_motor_ia_genera_analisis_critico_por_desgaste():
    from analisis_ia import _motor_experto_calidad_ia, realizar_analisis_ia

    metricas_criticas = {
        "modelo_ml": "RedNeuronalIA_v1",
        "piezas_evaluadas": 25,
        "piezas_en_riesgo": 10,
        "tasa_riesgo_pct": 40.0,
        "riesgo_promedio": 0.65,
        "desgaste_herramienta_max": 295,
        "temperatura_media_c": 22.5,
        "decision_operativa": "CAMBIAR HERRAMIENTA",
        "nivel_urgencia": "ALTO",
        "umbral_decision": 0.80,
    }

    resultado = _motor_experto_calidad_ia(metricas_criticas)
    assert "ESTADO CRÍTICO" in resultado["resumen_ejecutivo"]
    assert "Desgaste crítico" in resultado["analisis_detallado"]
    assert "INTERVENCIÓN INMEDIATA" in resultado["acciones_mantenimiento"]
    assert "Reemplazar el inserto" in resultado["acciones_mantenimiento"]

    informe = realizar_analisis_ia(metricas_criticas)
    assert informe["decision_operativa"] == "CAMBIAR HERRAMIENTA"
    assert informe["piezas_evaluadas"] == 25
    assert len(informe["recomendaciones_produccion"]) > 20


def test_motor_ia_genera_analisis_estable():
    from analisis_ia import realizar_analisis_ia

    metricas_estables = {
        "modelo_ml": "RedNeuronalIA_v1",
        "piezas_evaluadas": 20,
        "piezas_en_riesgo": 1,
        "tasa_riesgo_pct": 5.0,
        "riesgo_promedio": 0.12,
        "desgaste_herramienta_max": 60,
        "temperatura_media_c": 21.0,
        "decision_operativa": "CONTINUAR",
        "nivel_urgencia": "BAJO",
        "umbral_decision": 0.80,
    }

    informe = realizar_analisis_ia(metricas_estables)
    assert informe["nivel_urgencia"] == "BAJO"
    assert "OPERACIÓN ESTABLE" in informe["resumen_ejecutivo"]
    assert "Continuar producción estándar" in informe["acciones_mantenimiento"]
    assert "estabilizar" in informe["recomendaciones_produccion"].lower() or "ciclos" in informe["recomendaciones_produccion"].lower()


if __name__ == "__main__":
    funciones = [
        obj
        for name, obj in list(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    print(f"Ejecutando {len(funciones)} pruebas de ML...")
    for fn in funciones:
        fn()
        print(f"  [PASS] {fn.__name__}")
    print(f"\n¡Todas las {len(funciones)} pruebas pasaron exitosamente!")
