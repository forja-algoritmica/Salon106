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

# 5. Guardar las decisiones en la base (para el tablero)
python ml\registrar_decisiones.py

# 6. Detección de anomalías (sin etiquetas)
python ml\detectar_anomalias.py

# 7. Regresión del valor de una cota
python ml\regresion_cota.py --listar
python ml\regresion_cota.py --cota cota_plm_c01

# 8. Pruebas automáticas
python -m pytest tests -q
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

## Decisiones guardadas en la base

`registrar_decisiones.py` calcula el riesgo de todas las piezas y lo guarda en
`calidad_piezas.decisiones`, para que el tablero y la auditoría tengan el dato:

```powershell
python ml\registrar_decisiones.py
python ml\registrar_decisiones.py --reemplazar   # recalcula desde cero
```

| Columna | Contenido |
|---|---|
| `id_revision` | Pieza evaluada (único: una decisión por pieza) |
| `probabilidad` | Riesgo estimado por el modelo |
| `umbral` | Umbral usado en esa corrida |
| `decision` | `CONTINUAR`, `REVISAR PIEZA` o `CAMBIAR HERRAMIENTA` |
| `motivo` | Explicación corta de la decisión |
| `modelo` | Archivo del modelo que la generó |
| `generado_en` | Cuándo se calculó |

Para Power BI existe la vista `public.v_decisiones`, que ya une la decisión con
la pieza, la fecha y el resultado real.

**Ejemplo con un mes de datos** (5.040 piezas):

| Decisión | Cantidad | Riesgo medio | Desgaste | Rechazo real |
|---|---|---|---|---|
| CONTINUAR | 4.432 | 0,19 | 0–299 | 1,5 % |
| REVISAR PIEZA | 525 | 0,82 | 196–299 | 10,9 % |
| CAMBIAR HERRAMIENTA | 83 | 0,92 | 244–299 | 20,5 % |

Las piezas marcadas para cambio de herramienta tienen **7 veces más** probabilidad
de estar defectuosas que el promedio: eso es lo que hace útil la tabla.

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
