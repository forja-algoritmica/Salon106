"""Análisis inteligente con IA y recomendaciones de mejora en la producción.

Este módulo toma los resultados y predicciones del modelo de Machine Learning,
evalúa el estado de la línea de producción y utiliza Inteligencia Artificial
(Gemini / OpenAI o motor experto de calidad industrial) para generar un informe
exhaustivo con diagnóstico de causas raíz, riesgos de calidad, recomendaciones
operativas inmediatas y propuestas de mejora en la producción.

El resultado se inserta automáticamente en la tabla `analisis_ia_produccion`
de Supabase / PostgreSQL.

Uso:
    python ml/analisis_ia.py
    python ml/analisis_ia.py --ultimas 30
    python ml/analisis_ia.py --no-guardar
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from conexion_supabase import consultar, ejecutar, obtener_conexion, obtener_parametros
from predecir_interactivo import VENTANA_TENDENCIA, cargar_modelo, decidir

TABLA_ANALISIS = "analisis_ia_produccion"
PIEZAS_EVALUAR_POR_DEFECTO = int(os.getenv("IA_PIEZAS_EVALUAR", "1000"))


# ---------------------------------------------------------------------------
# Gestión de la tabla en base de datos
# ---------------------------------------------------------------------------
def garantizar_tabla_analisis() -> None:
    """Crea la tabla de análisis en la base de datos si aún no existe."""
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {TABLA_ANALISIS} (
        id_analisis SERIAL PRIMARY KEY,
        fecha_analisis TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        modelo_ml VARCHAR(100) NOT NULL,
        piezas_evaluadas INTEGER NOT NULL,
        piezas_en_riesgo INTEGER NOT NULL,
        tasa_riesgo_pct NUMERIC(5, 2) NOT NULL,
        desgaste_herramienta_max INTEGER,
        temperatura_media_c NUMERIC(6, 2),
        decision_operativa VARCHAR(50) NOT NULL,
        nivel_urgencia VARCHAR(20) NOT NULL,
        resumen_ejecutivo TEXT NOT NULL,
        analisis_detallado TEXT NOT NULL,
        recomendaciones_produccion TEXT NOT NULL,
        acciones_mantenimiento TEXT NOT NULL,
        motor_ia VARCHAR(60) NOT NULL,
        metricas_json JSONB
    );
    """
    try:
        ejecutar(ddl)
    except Exception as exc:
        # En caso de que el tipo JSONB no sea soportado por alguna versión, intentar con TEXT
        if "jsonb" in str(exc).lower():
            ddl_fallback = ddl.replace("JSONB", "TEXT")
            ejecutar(ddl_fallback)
        else:
            raise exc


def guardar_analisis_en_bd(datos: dict[str, Any]) -> int | None:
    """Inserta el análisis generado por la IA en la base de datos."""
    garantizar_tabla_analisis()

    sql = f"""
    INSERT INTO {TABLA_ANALISIS} (
        modelo_ml,
        piezas_evaluadas,
        piezas_en_riesgo,
        tasa_riesgo_pct,
        desgaste_herramienta_max,
        temperatura_media_c,
        decision_operativa,
        nivel_urgencia,
        resumen_ejecutivo,
        analisis_detallado,
        recomendaciones_produccion,
        acciones_mantenimiento,
        motor_ia,
        metricas_json
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    RETURNING id_analisis;
    """
    parametros = (
        datos["modelo_ml"],
        int(datos["piezas_evaluadas"]),
        int(datos["piezas_en_riesgo"]),
        float(datos["tasa_riesgo_pct"]),
        int(datos.get("desgaste_herramienta_max") or 0),
        float(datos.get("temperatura_media_c") or 0.0),
        datos["decision_operativa"],
        datos["nivel_urgencia"],
        datos["resumen_ejecutivo"],
        datos["analisis_detallado"],
        datos["recomendaciones_produccion"],
        datos["acciones_mantenimiento"],
        datos["motor_ia"],
        json.dumps(datos.get("metricas_json", {}), ensure_ascii=False),
    )

    con = obtener_conexion()
    try:
        cur = con.cursor()
        cur.execute(sql, parametros)
        fila = cur.fetchone()
        con.commit()
        id_generado = fila[0] if fila else None
        cur.close()
        return id_generado
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Recopilación de métricas desde el modelo ML y la BD
# ---------------------------------------------------------------------------
def extraer_metricas_ml(ultimas_n: int = PIEZAS_EVALUAR_POR_DEFECTO) -> dict[str, Any]:
    """Carga el modelo de ML, realiza inferencia y consolida las métricas."""
    red, pre, estado = cargar_modelo()
    if red is None:
        raise RuntimeError("No hay modelo entrenado disponible para análisis.")

    tabla_nombre = estado.get("tabla", "v_riesgo_piezas")
    umbral = float(estado.get("umbral", 0.5))

    from conexion_supabase import cargar_datos_tabla

    tabla = cargar_datos_tabla(tabla_nombre)
    if len(tabla) == 0:
        raise RuntimeError(f"No hay registros en la tabla/vista '{tabla_nombre}'.")

    X = pre.transformar_nuevos_datos(tabla)
    probabilidades = red.predecir_probabilidad(X).ravel()

    if hasattr(tabla, "columns"):
        columnas = list(tabla.columns)
        filas = tabla.values.tolist()
    else:
        columnas = tabla.columnas
        filas = tabla.filas

    i_desgaste = (
        columnas.index("piezas_en_herramienta")
        if "piezas_en_herramienta" in columnas
        else None
    )
    i_temp = (
        columnas.index("temperatura_c") if "temperatura_c" in columnas else None
    )
    i_pieza = (
        columnas.index("codigo_pieza") if "codigo_pieza" in columnas else None
    )

    # Ordenar por desgaste si está disponible; de lo contrario, orden secuencial
    if i_desgaste is not None:
        orden = sorted(range(len(filas)), key=lambda i: filas[i][i_desgaste] or 0)
    else:
        orden = list(range(len(filas)))

    ultimas_idx = orden[-ultimas_n:]
    piezas_en_riesgo = 0
    desgastes = []
    temperaturas = []
    piezas_detalle = []

    for i in ultimas_idx:
        p_riesgo = float(probabilidades[i])
        desgaste = int(filas[i][i_desgaste]) if i_desgaste is not None else 0
        temp = float(filas[i][i_temp]) if i_temp is not None else 0.0
        codigo = str(filas[i][i_pieza]) if i_pieza is not None else f"P-{i}"
        decision = decidir(p_riesgo, umbral)

        if p_riesgo >= umbral:
            piezas_en_riesgo += 1

        desgastes.append(desgaste)
        if temp > 0:
            temperaturas.append(temp)

        piezas_detalle.append(
            {
                "codigo": codigo,
                "riesgo": round(p_riesgo, 4),
                "desgaste": desgaste,
                "temperatura": round(temp, 2),
                "decision": decision,
            }
        )

    riesgo_promedio = (
        sum(p["riesgo"] for p in piezas_detalle) / len(piezas_detalle) if piezas_detalle else 0.0
    )
    desgaste_max = max(desgastes) if desgastes else 0
    desgaste_prom = sum(desgastes) / len(desgastes) if desgastes else 0.0
    temp_media = sum(temperaturas) / len(temperaturas) if temperaturas else 0.0
    tasa_riesgo_pct = (piezas_en_riesgo / len(piezas_detalle)) * 100 if piezas_detalle else 0.0

    # Decisión operativa consolidada
    if riesgo_promedio >= 0.5 or piezas_en_riesgo >= len(piezas_detalle) * 0.5:
        decision_global = "CAMBIAR HERRAMIENTA"
        urgencia = "CRITICO" if riesgo_promedio >= 0.75 else "ALTO"
    elif riesgo_promedio >= umbral * 0.7 or piezas_en_riesgo >= len(piezas_detalle) * 0.25:
        decision_global = "REVISAR PIEZA"
        urgencia = "MEDIO"
    else:
        decision_global = "CONTINUAR"
        urgencia = "BAJO"

    return {
        "modelo_ml": "RedNeuronalIA_v1 (Perceptrón Multicapa)",
        "tabla_origen": tabla_nombre,
        "umbral_decision": umbral,
        "piezas_evaluadas": len(piezas_detalle),
        "piezas_en_riesgo": piezas_en_riesgo,
        "tasa_riesgo_pct": round(tasa_riesgo_pct, 2),
        "riesgo_promedio": round(riesgo_promedio, 4),
        "desgaste_herramienta_max": desgaste_max,
        "desgaste_herramienta_promedio": round(desgaste_prom, 1),
        "temperatura_media_c": round(temp_media, 2),
        "decision_operativa": decision_global,
        "nivel_urgencia": urgencia,
        "muestras": piezas_detalle[-10:],
    }


# ---------------------------------------------------------------------------
# Motor de Inferencia y Generación con IA
# ---------------------------------------------------------------------------
def _generar_con_gemini(metricas: dict[str, Any], api_key: str) -> dict[str, Any] | None:
    """Consulta la API de Google Gemini para un análisis profundo."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    prompt = f"""
Eres el Ingeniero Principal de Calidad y Confiabilidad de Procesos de Manufactura en una planta industrial metalmecánica avanzada (normas IATF 16949 / ISO 9001).
Acabas de recibir las métricas de inferencia generadas por el modelo de Machine Learning de la línea:

{json.dumps(metricas, indent=2, ensure_ascii=False)}

Genera un reporte técnico de alto nivel estructurado en formato JSON con exactamente estas claves:
{{
  "resumen_ejecutivo": "Diagnóstico conciso del lote analizado y estado de la línea",
  "analisis_detallado": "Análisis técnico profundo de factores causales (desgaste de herramientas, comportamiento térmico, estabilidad del proceso y riesgos de no conformidad dimensional)",
  "recomendaciones_produccion": "Estrategias de mejora continua para optimizar el rendimiento, reducir defectos (scrap) y mejorar el OEE y Cp/Cpk",
  "acciones_mantenimiento": "Acciones operativas y preventivas inmediatas para el equipo de planta (herramental, lubricación, calibración, inspección)",
  "nivel_urgencia": "BAJO | MEDIO | ALTO | CRITICO"
}}

Responde ÚNICAMENTE con el objeto JSON válido, sin delimitadores de código markdown adicionales.
"""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=25) as response:
        if response.status == 200:
            resultado_raw = json.loads(response.read().decode("utf-8"))
            texto = resultado_raw["candidates"][0]["content"]["parts"][0]["text"].strip()
            # Limpiar posibles bloques markdown si vinieran
            if texto.startswith("```json"):
                texto = texto[7:]
            if texto.startswith("```"):
                texto = texto[3:]
            if texto.endswith("```"):
                texto = texto[:-3]
            return json.loads(texto.strip())
    return None


def _generar_con_openai(metricas: dict[str, Any], api_key: str) -> dict[str, Any] | None:
    """Consulta la API de OpenAI (GPT-4o-mini)."""
    url = "https://api.openai.com/v1/chat/completions"
    prompt = f"""
Eres el Ingeniero Principal de Calidad y Procesos de Manufactura.
Con base en los siguientes datos del modelo de Machine Learning:
{json.dumps(metricas, indent=2, ensure_ascii=False)}

Genera un reporte técnico en formato JSON estricto con las siguientes claves:
{{
  "resumen_ejecutivo": "...",
  "analisis_detallado": "...",
  "recomendaciones_produccion": "...",
  "acciones_mantenimiento": "...",
  "nivel_urgencia": "BAJO | MEDIO | ALTO | CRITICO"
}}
"""
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Experto en calidad y manufactura Six Sigma."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=25) as response:
        if response.status == 200:
            resultado_raw = json.loads(response.read().decode("utf-8"))
            texto = resultado_raw["choices"][0]["message"]["content"].strip()
            return json.loads(texto)
    return None


def _motor_experto_calidad_ia(metricas: dict[str, Any]) -> dict[str, Any]:
    """Motor de análisis experto basado en reglas de ingeniería de manufactura y control estadístico.

    Se ejecuta de forma local y autónoma, garantizando confiabilidad y disponibilidad 100%
    incluso si no hay claves de API externas o la máquina no tiene acceso a internet.
    """
    total = metricas["piezas_evaluadas"]
    riesgo_pct = metricas["tasa_riesgo_pct"]
    riesgo_prom = metricas["riesgo_promedio"]
    desgaste_max = metricas["desgaste_herramienta_max"]
    temp_media = metricas["temperatura_media_c"]
    decision = metricas["decision_operativa"]
    urgencia = metricas["nivel_urgencia"]

    # 1. Resumen ejecutivo
    if decision == "CAMBIAR HERRAMIENTA":
        resumen = (
            f"ESTADO CRÍTICO DE LÍNEA: Se detectó un riesgo acumulado elevado del {riesgo_pct:.1f}% "
            f"sobre {total} piezas evaluadas, con un desgaste máximo de {desgaste_max} ciclos en herramienta. "
            f"El modelo de ML señala agotamiento de vida útil del inserto de corte y alta probabilidad "
            f"de desviación dimensional fuera de tolerancias de plano."
        )
    elif decision == "REVISAR PIEZA":
        resumen = (
            f"PRECAUCIÓN OPERATIVA: Tasa de riesgo moderada ({riesgo_pct:.1f}%), riesgo medio de {riesgo_prom * 100:.1f}% "
            f"y desgaste de {desgaste_max} ciclos. El proceso se encuentra cerca del umbral de control estadístico. "
            f"Se requiere verificación metrológica intermedia para prevenir piezas no conformes."
        )
    else:
        resumen = (
            f"OPERACIÓN ESTABLE Y BAJO CONTROL: Proceso en condiciones óptimas de repetibilidad. "
            f"Riesgo medio de {riesgo_prom * 100:.1f}% con {riesgo_pct:.1f}% de piezas en vigilancia. "
            f"Las variables térmicas ({temp_media:.1f} °C) y mecánicas se mantienen dentro de la ventana nominal."
        )

    # 2. Análisis detallado
    causas = []
    if desgaste_max >= 250:
        causas.append(
            f"• Desgaste crítico de herramienta ({desgaste_max} piezas acumuladas): la microfalla del filo "
            "genera incremento en fuerzas de corte, deflexión de la pieza y deriva dimensional en cotas críticas."
        )
    elif desgaste_max >= 150:
        causas.append(
            f"• Desgaste en zona de transición ({desgaste_max} piezas): el filo presenta desgaste de flanco "
            "medible que puede aproximarse al límite de tolerancia."
        )
    else:
        causas.append(
            f"• Vida útil de herramienta en régimen normal ({desgaste_max} piezas): desgaste uniforme dentro de parámetros."
        )

    if temp_media > 25.0:
        causas.append(
            f"• Deriva térmica significativa ({temp_media:.1f} °C): gradiente térmico elevado susceptible de "
            "causar dilatación lineal en bancada y piezas, afectando el centrado y cotas de referencia."
        )
    elif temp_media < 19.0:
        causas.append(
            f"• Temperatura por debajo de régimen ideal ({temp_media:.1f} °C): verificar calentamiento previo "
            "de husillos y estabilidad del fluido de corte."
        )
    else:
        causas.append(
            f"• Estabilidad térmica adecuada ({temp_media:.1f} °C): mínima influencia de dilatación en el mecanizado."
        )

    causas.append(
        f"• Dinámica del modelo predictivo: Umbral de corte fijado en {metricas['umbral_decision']:.2f}. "
        f"Las covariables de máquina predicen el comportamiento de tolerancia previo a la medición en CMM."
    )

    analisis_detallado = "\n".join(causas)

    # 3. Recomendaciones de mejora en la producción
    recomendaciones = [
        "1. Estandarización de ciclos de herramental: Fijar límite preventivo de vida útil en 250-280 ciclos "
        "para evitar la fase de desgaste acelerado.",
        "2. Monitoreo térmico continuo: Regular el sistema de refrigeración y caudal de taladrina para "
        "mantener la temperatura de corte entre 20 °C y 23 °C.",
        "3. Optimización OEE y reducción de Scrap: Implementar parada programada preventiva ante alertas "
        "tempranas de la red neuronal antes de que se produzca una pieza rechazada.",
        "4. Control de calidad Six Sigma: Realizar estudios de capacidad de proceso (Cp y Cpk) en las "
        "cotas con mayor correlación a desgaste para estrechar tolerancias operativas.",
    ]
    recomendaciones_produccion = "\n".join(recomendaciones)

    # 4. Acciones de mantenimiento
    if decision == "CAMBIAR HERRAMIENTA":
        acciones = [
            "• INTERVENCIÓN INMEDIATA: Parar la máquina al finalizar la pieza en curso.",
            "• Reemplazar el inserto/fresa de corte e inspeccionar el cono portaherramientas.",
            "• Reiniciar el contador de piezas en herramienta a 0 en el sistema de control.",
            "• Realizar inspección dimensional CMM al 100% en la primera pieza producida tras el cambio.",
        ]
    elif decision == "REVISAR PIEZA":
        acciones = [
            "• Realizar inspección visual y metrológica en las próximas 3 piezas de la serie.",
            "• Preparar herramienta de repuesto y preajustador para el próximo relevo de turno o paro.",
            "• Comprobar presión y dirección de las boquillas de refrigerante sobre el filo de corte.",
        ]
    else:
        acciones = [
            "• Continuar producción estándar sin detenciones.",
            "• Mantener rutina de lubricación y limpieza de virutas programada.",
            "• Registrar parámetros de corte en la bitácora de turno.",
        ]
    acciones_mantenimiento = "\n".join(acciones)

    return {
        "resumen_ejecutivo": resumen,
        "analisis_detallado": analisis_detallado,
        "recomendaciones_produccion": recomendaciones_produccion,
        "acciones_mantenimiento": acciones_mantenimiento,
        "nivel_urgencia": urgencia,
    }


def realizar_analisis_ia(metricas: dict[str, Any]) -> dict[str, Any]:
    """Orquesta la generación del análisis con la mejor IA disponible."""
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    resultado = None
    motor_utilizado = "Motor Experto de Calidad y Procesos IA (Local)"

    # 1. Intentar Gemini si hay API key
    if gemini_key:
        try:
            resultado = _generar_con_gemini(metricas, gemini_key)
            if resultado and "resumen_ejecutivo" in resultado:
                motor_utilizado = "Google Gemini 1.5 Flash (Cloud)"
        except Exception as exc:
            print(f"[IA] Aviso: Falló consulta a Gemini API ({exc}). Usando motor de respaldo.")

    # 2. Intentar OpenAI si hay API key y Gemini no se usó
    if resultado is None and openai_key:
        try:
            resultado = _generar_con_openai(metricas, openai_key)
            if resultado and "resumen_ejecutivo" in resultado:
                motor_utilizado = "OpenAI GPT-4o-mini (Cloud)"
        except Exception as exc:
            print(f"[IA] Aviso: Falló consulta a OpenAI API ({exc}). Usando motor de respaldo.")

    # 3. Fallback al motor experto local de calidad industrial
    if resultado is None:
        resultado = _motor_experto_calidad_ia(metricas)

    # Consolidar objeto completo
    analisis_completo = {
        "modelo_ml": metricas["modelo_ml"],
        "piezas_evaluadas": metricas["piezas_evaluadas"],
        "piezas_en_riesgo": metricas["piezas_en_riesgo"],
        "tasa_riesgo_pct": metricas["tasa_riesgo_pct"],
        "desgaste_herramienta_max": metricas.get("desgaste_herramienta_max"),
        "temperatura_media_c": metricas.get("temperatura_media_c"),
        "decision_operativa": metricas["decision_operativa"],
        "nivel_urgencia": resultado.get("nivel_urgencia", metricas["nivel_urgencia"]),
        "resumen_ejecutivo": resultado.get("resumen_ejecutivo", ""),
        "analisis_detallado": resultado.get("analisis_detallado", ""),
        "recomendaciones_produccion": resultado.get("recomendaciones_produccion", ""),
        "acciones_mantenimiento": resultado.get("acciones_mantenimiento", ""),
        "motor_ia": motor_utilizado,
        "metricas_json": metricas,
        "fecha": datetime.now(timezone.utc).isoformat(),
    }
    return analisis_completo


# ---------------------------------------------------------------------------
# Flujo principal de ejecución
# ---------------------------------------------------------------------------
def ejecutar_analisis_completo(
    ultimas_piezas: int = PIEZAS_EVALUAR_POR_DEFECTO, guardar: bool = True
) -> dict[str, Any]:
    """Ejecuta el pipeline completo: extracción de métricas ML -> análisis IA -> inserción en BD."""
    print("=" * 76)
    print(" ANÁLISIS DE CALIDAD Y MEJORA DE PRODUCCIÓN CON INTELIGENCIA ARTIFICIAL")
    print("=" * 76)

    print("\n1. Extrayendo métricas de inferencia del modelo Machine Learning...")
    metricas = extraer_metricas_ml(ultimas_n=ultimas_piezas)
    print(f"   • Modelo evaluado       : {metricas['modelo_ml']}")
    print(f"   • Piezas analizadas     : {metricas['piezas_evaluadas']}")
    print(f"   • Piezas en riesgo alto : {metricas['piezas_en_riesgo']} ({metricas['tasa_riesgo_pct']} %)")
    print(f"   • Desgaste máximo       : {metricas['desgaste_herramienta_max']} ciclos")
    print(f"   • Temperatura media     : {metricas['temperatura_media_c']} °C")
    print(f"   • Decisión preliminar   : {metricas['decision_operativa']}")

    print("\n2. Generando análisis detallado y recomendaciones con IA...")
    informe = realizar_analisis_ia(metricas)
    print(f"   • Motor utilizado       : {informe['motor_ia']}")
    print(f"   • Nivel de urgencia     : {informe['nivel_urgencia']}")

    print("\n" + "-" * 76)
    print(" RESUMEN EJECUTIVO:")
    print("-" * 76)
    print(informe["resumen_ejecutivo"])

    print("\n" + "-" * 76)
    print(" ANÁLISIS DETALLADO DE PRODUCCIÓN:")
    print("-" * 76)
    print(informe["analisis_detallado"])

    print("\n" + "-" * 76)
    print(" RECOMENDACIONES DE MEJORA EN LA PRODUCCIÓN:")
    print("-" * 76)
    print(informe["recomendaciones_produccion"])

    print("\n" + "-" * 76)
    print(" ACCIONES DE MANTENIMIENTO:")
    print("-" * 76)
    print(informe["acciones_mantenimiento"])
    print("-" * 76)

    if guardar:
        print("\n3. Insertando informe y recomendaciones en la base de datos...")
        try:
            id_insertado = guardar_analisis_en_bd(informe)
            print(f"   ¡Guardado con éxito! Registro #{id_insertado} en tabla '{TABLA_ANALISIS}'.")
            informe["id_analisis"] = id_insertado
        except Exception as exc:
            print(f"   [Error al guardar en BD]: {exc}")
            raise exc
    else:
        print("\n[Modo prueba] No se guardó en base de datos (--no-guardar).")

    print("\n" + "=" * 76)
    return informe


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genera un análisis con IA y recomendaciones para la producción tras el análisis ML"
    )
    parser.add_argument(
        "--ultimas",
        type=int,
        default=PIEZAS_EVALUAR_POR_DEFECTO,
        help="Número de piezas recientes a considerar en la evaluación (por defecto 1000)",
    )
    parser.add_argument(
        "--no-guardar",
        action="store_true",
        help="Solo muestra el análisis en pantalla sin escribir en la base de datos",
    )
    args = parser.parse_args()

    try:
        ejecutar_analisis_completo(ultimas_piezas=args.ultimas, guardar=not args.no_guardar)
        return 0
    except Exception as exc:
        print(f"\nError durante la ejecución del análisis con IA: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

