# Machine Learning — Riesgo de piezas defectuosas

Pipeline que se conecta a Supabase, entrena una red neuronal con datos reales
de la línea y emite **decisiones operativas** (continuar, revisar la pieza o
cambiar la herramienta).

## Dependencias

Solo **numpy** y **pg8000** (Python puro). No se usa pandas, SQLAlchemy ni
psycopg a propósito: sus extensiones compiladas quedan bloqueadas por las
políticas de control de aplicaciones (WDAC) de algunos equipos, y así el mismo
código corre en Windows restringido y en el contenedor Linux.

```powershell
pip install -r ml\requirements.txt
```

## Configuración

Todo se lee del `.env` de la raíz del repositorio (lo genera
`tools/configurar_bd.py`):

```env
DB_HOST=aws-0-us-east-2.pooler.supabase.com
DB_PORT=5432
DB_NAME=postgres
DB_USER=pipeline_rw.<proyecto>
DB_PASSWORD=...
DB_SCHEMA=public
DB_TABLE=v_entrenamiento_piezas
DB_TARGET=defectuosa
```

## Las dos vistas de datos

El esquema `calidad_piezas` guarda las mediciones normalizadas (una fila por
cota). Para el ML se exponen dos vistas en `public`:

| Vista | Contenido | Para qué sirve |
|---|---|---|
| `v_entrenamiento_piezas` | Una fila por pieza con las **82 cotas** medidas | Clasificar y validar la inspección |
| `v_riesgo_piezas` | Solo **covariables**: temperatura, desgaste y hora | Predecir el riesgo **antes** de medir |

> Usar `v_entrenamiento_piezas` para predecir es hacer trampa: la pieza se
> rechaza justamente porque una de esas cotas está fuera de tolerancia. El
> modelo aprende la tolerancia, no a anticiparse. Para decisiones sirve
> `v_riesgo_piezas`.

La variable objetivo es `defectuosa` (1 = rechazada), siempre la última columna.

## Comandos

```powershell
# 1. Preparar base de datos, roles y vistas (una sola vez)
python tools\configurar_bd.py

# 2. Inspeccionar objetos disponibles
python ml\conexion_supabase.py

# 3. Entrenar
python ml\entrenar_con_supabase.py --tabla v_riesgo_piezas

# 4. Predecir y decidir sobre las piezas recientes
python ml\predecir_interactivo.py --ultimas 20

# 5. Análisis detallado con IA y recomendaciones (guarda en BD)
python ml\analisis_ia.py
python ml\analisis_ia.py --ultimas 30

# 6. Detección de anomalías (sin etiquetas)
python ml\detectar_anomalias.py

# 7. Regresión del valor de una cota
python ml\regresion_cota.py --listar
python ml\regresion_cota.py --cota cota_plm_c01

# 8. Pruebas automáticas
python tests\test_ml.py
```

## Qué hace el entrenamiento

1. Descarga la vista elegida.
2. Preprocesa: imputa nulos, normaliza (Z-score) y codifica categóricas
   (one-hot). Descarta columnas de más de 50 categorías.
3. Divide **60 / 20 / 20**: entrenamiento, validación (umbral) y prueba.
4. **Sobremuestrea** la clase minoritaria: sin esto, decir siempre "conforme"
   acierta el 97 % y el modelo no aprende nada.
5. Entrena la red (2 capas ocultas ReLU, salida sigmoide, backpropagation).
6. Elige el **umbral de decisión** que maximiza F1 sobre validación.
7. Guarda pesos (`.npz`) y preprocesamiento + umbral (`.json`).

## Resultados de referencia

Con 330 ensambles (2 310 piezas, 68 defectuosas, 2,94 %) y desgaste marcado:

| Métrica | Valor |
|---|---|
| Exactitud | 86,4 % |
| Recall (defectos detectados) | **71,4 %** |
| Precisión | 14,5 % |
| F1 | 24,1 % |

La precisión parece baja, pero el evento es raro: la tasa base es 2,94 %, así
que 14,5 % es **5 veces mejor que el azar**. Para mantenimiento lo que importa
es el recall: se detectan 7 de cada 10 piezas malas.

## Lógica de decisión

`predecir_interactivo.py` traduce la probabilidad en una acción:

| Riesgo | Decisión |
|---|---|
| ≥ umbral + 0,15 | **CAMBIAR HERRAMIENTA** |
| ≥ umbral | **REVISAR PIEZA** |
| < umbral | **CONTINUAR** |

Además evalúa la tendencia de las últimas 25 piezas: si el riesgo medio supera
0,5 o más de la mitad están sobre el umbral, recomienda cambiar la herramienta
aunque ninguna pieza aislada lo dispare.

## Análisis detallado con IA y Recomendaciones de Producción (`analisis_ia.py`)

Después de que el modelo de Machine Learning computa los riesgos de no conformidad y las tendencias de desgaste/temperatura, el módulo `analisis_ia.py` sintetiza todos los indicadores y genera un **diagnóstico exhaustivo asistido por IA**, proporcionando:

1. **Diagnóstico y resumen ejecutivo**: Estado de la línea y criticidad del lote actual.
2. **Análisis técnico causa-raíz**: Correlación de desgaste de herramental, derivas térmicas y deflexiones en cotas críticas.
3. **Recomendaciones de mejora en la producción**: Optimización de parámetros de corte, ciclos de vida de herramientas y control de OEE/Scrap.
4. **Acciones de mantenimiento**: Instrucciones operativas inmediatas (parada de máquina, reemplazo de inserto, calibración o continuación).
5. **Registro automático en base de datos**: Inserta cada análisis en la tabla `analisis_ia_produccion` con timestamp, métricas clave, nivel de urgencia (`BAJO`, `MEDIO`, `ALTO`, `CRITICO`) y detalle JSON.

### Motores de IA soportados
- **Google Gemini** (`GEMINI_API_KEY` o `GOOGLE_API_KEY`): Generación avanzada con `gemini-1.5-flash`.
- **OpenAI** (`OPENAI_API_KEY`): Compatible con `gpt-4o-mini`.
- **Motor Experto de Calidad y Procesos IA (Local)**: Motor heurístico integrado de ingeniería de manufactura Six Sigma / IATF 16949 que opera de forma autónoma y sin dependencias externas, garantizando que el pipeline nunca falle si no hay internet o credenciales en la nube.

### Estructura de la tabla `analisis_ia_produccion` en Supabase
```sql
CREATE TABLE analisis_ia_produccion (
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
```

## Detección de anomalías (sin etiquetas)

`detectar_anomalias.py` aprende cómo luce una pieza normal **solo con las
conformes** y marca las que se alejan del patrón, sin usar la etiqueta. Sirve
cuando no hay histórico de rechazos.

Método: puntaje z por cota (`z = (valor − media) / desviación`), ajustado con
las piezas aprobadas. Por pieza se calculan dos indicadores:

- **max |z|**: la cota más rara (detecta un valor atípico aislado).
- **RMS de z**: pieza desplazada en varias cotas a la vez.

El umbral se fija con el percentil 99,5 de la propia población conforme.

Resultado con los datos actuales:

| Métrica | Valor |
|---|---|
| Anomalías marcadas | 45 de 2 331 |
| Defectos detectados | 22 de 68 (recall 32,4 %) |
| Precisión | **48,9 %** |
| Conformes pero atípicas | 23 (aviso temprano) |

Sin ninguna etiqueta, la precisión (48,9 %) es **tres veces mejor** que la del
modelo supervisado. Es el enfoque adecuado cuando el rechazo es raro.

## Regresión del valor de una cota

`regresion_cota.py` ajusta `valor = b0 + b1·temperatura + b2·desgaste` por
mínimos cuadrados y compara los coeficientes con la física del simulador.

Ejemplo real (`cota_plm_c01`, nominal 4 525 mm):

```
valor = 4524.199 + 0.0398 * temperatura + 0.00206 * desgaste
R²  = 0.356      MAE = 0.236 mm

dilatación   medida 0.03984 vs teórica 0.05204 mm/°C
deriva       medida 0.00206 vs teórica 0.00301 mm/pieza
```

La regresión recupera la estructura causal (dilatación térmica y desgaste), no
una correlación espuria. El R² bajo es esperable: el ruido de medición domina
frente a esos efectos.

## Pruebas

```powershell
python -m pytest tests -q
```

17 pruebas que no tocan la base de datos. Ver el detalle en el
[README principal](../README.md#cómo-ejecutar-las-pruebas).

## Limitación importante del simulador

Con la configuración de fábrica, los defectos son **casi todos aleatorios**
(eventos puntuales, valores atípicos), así que **ningún modelo puede
anticiparlos**: la tasa de defecto es plana frente al desgaste (8,0 % al inicio
y 8,6 % al final de la vida de la herramienta).

Para que el modelo tenga algo que aprender, el generador incluye deriva por
desgaste. El perfil usado para entrenar (`app/config/proceso.json`) aplica:

```json
"deriva_total_sigmas": 3.0,
"escala": 0.05
```

Con eso la tasa sube de 0 % al inicio a 10,9 % al final de la vida útil y el
modelo aprende el patrón. Si se vuelve a la configuración realista, el modelo
de riesgo pierde prácticamente toda su capacidad predictiva; eso es un
resultado válido, no un fallo del código.
