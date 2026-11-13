# Flujo completo: de cero a decisiones

Guía para ejecutar y verificar todo el pipeline en orden. Cada paso indica qué
debe salir y cómo saber que está bien.

> No hace falta el `.exe` ni Docker. Todo corre con Python.

---

## Antes de empezar

```powershell
cd "C:\Users\Edwin Quiroz\Salon106"
python --version        # 3.10 o superior
python -m pytest --version
```

Si falta pytest: `pip install pytest`.

---

## Paso 1 — Pruebas automáticas

**Doble clic:** `Ejecutar pruebas.bat`

**Consola:**

```powershell
python -m pytest tests -q
```

**Qué verás:**

```
.................                                                        [100%]
17 passed in 0.22s
```

**Qué está comprobando:** catálogo (7 piezas, 82 cotas), generación, división
estratificada, umbral, decisiones, anomalías y regresión. No toca la base de
datos.

Las pruebas del generador son otras 27:

```powershell
cd "..\linea_produccion"
python -m pytest -q
```

---

## Paso 2 — Preparar la base (solo la primera vez)

```powershell
python tools\configurar_bd.py
```

**Qué hace:** agrega columnas de analítica, crea índices, los roles
`pipeline_rw` y `powerbi_ro`, las dos vistas de ML y escribe el `.env`.

Es idempotente: se puede repetir sin borrar datos.

**Cómo verificarlo:**

```powershell
python ml\conexion_supabase.py
```

Debe listar `v_entrenamiento_piezas` y `v_riesgo_piezas`.

---

## Paso 3 — Generar datos

**Doble clic:** `Ejecutar generador.bat`

**Consola** (20 ensambles y termina):

```powershell
python app\generador_datos.py --flujos 20
```

**Para un histórico de un mes** (los ensambles se reparten en las fechas):

```powershell
python app\generador_datos.py --dias 30 --flujos 720      # uno cada hora
python app\generador_datos.py --desde 2026-10-01 --hasta 2026-10-31 --flujos 744
```

El programa calcula el intervalo solo y arranca a las 06:00, con los turnos
rotando. Si la base ya tiene datos, avisa de que las fechas quedarían
desordenadas; conviene vaciarla antes (`--reiniciar`).

**Qué verás**, un bloque por ensamble:

```
FL-000123  11/11 19:09  T2  M. Torres  L-0003
  [1/7] BAS  Base              16/16 cotas    20,46 °C   OK
  [2/7] BR1  Brazo 1           13/14 cotas    21,47 °C   NOK
         >>> BR1-C03        611,150 mm   [609,500 – 610,500]  valor_atipico
  ...
  └── ARMADO   1 de 7 piezas NOK · valor_atipico          ENSAMBLE NOK   2,14 % NOK acumulado
```

**Cómo saber que escribe en la base:**

```powershell
python app\generador_datos.py --estado
```

```
Flujos registrados : 514
Piezas fabricadas  : 3598        (514 × 7)
Mediciones         : 42148       (514 × 82)
Cotas definidas    : 82
Piezas NOK         : 72
Tasa NOK           : 2,00 %
```

Las cuentas `piezas = flujos × 7` y `mediciones = flujos × 82` deben cuadrar.

---

## Paso 4 — Entrenar el modelo

**Doble clic:** `Ejecutar ML.bat` (hace los pasos 4, 5 y 6 de una vez)

**Consola:**

```powershell
python ml\entrenar_con_supabase.py --tabla v_riesgo_piezas
```

**Qué verás:** el preprocesamiento, el avance por épocas, el umbral elegido y el
informe final.

```
Clases: 72 no conformes de 3598 (2,00 %)
Línea base (decir siempre 'conforme'): 98,00 % de exactitud

Entrenamiento: 2158 (positivos 43) | Validación: 720 (positivos 15) | Prueba: 720 (positivos 14)

umbral elegido = 0.70 (validación: precisión 10,6 %, recall 53,8 %)

Exactitud general (Accuracy) : 86,36%
Precisión (Precision)        : 14,49%
Sensibilidad (Recall)        : 71,43%
Puntaje F1 (F1-Score)        : 24,10%
```

### Cómo leer estos números

| Métrica | Qué significa | Referencia |
|---|---|---|
| **Línea base** | Lo que acierta un modelo que dice siempre "conforme" | ~98 % (inútil) |
| **Exactitud** | Aciertos totales | Engañosa si hay desbalance |
| **Recall** | Qué porcentaje de las piezas malas detecta | **Lo más importante** |
| **Precisión** | Qué porcentaje de las alarmas son reales | Aquí ~14 %, 7× la base |
| **F1** | Equilibrio entre ambas | ~24 % |

> Una precisión de 14 % con una base de 2 % significa que **el modelo es 7 veces
> mejor que el azar**. No es un error: el evento es raro.

---

## Paso 5 — Detección de anomalías

```powershell
python ml\detectar_anomalias.py
```

```
Piezas analizadas       : 3598  (3526 conformes)
Cotas consideradas      : 82
Umbral max|z| (99.5 %)  : 3.31

Resultado de la alarma:
  anomalías marcadas      : 72
  defectos detectados     : 40 de 71 (recall 56,3 %)
  falsas alarmas          : 32 (precisión 55,6 %)

Piezas conformes pero atípicas: 23
```

Esto **no usa la etiqueta**: aprende cómo luce una pieza normal y marca las
raras. Su precisión suele ser mayor que la del modelo supervisado.

---

## Paso 6 — Regresión de una cota

```powershell
python ml\regresion_cota.py --listar
python ml\regresion_cota.py --cota cota_bas_c01
```

```
Cota        : cota_bas_c01  (componente BASE-001)
Muestras    : 514
  valor = 709.723 + 0.0119 * temperatura + 0.00072 * desgaste
  R²  = 0.198      MAE = 0.105

Comparación con la teoría:
  dilatación   medida 0.01189 vs teórica 0.00817 (mm/°C)
  deriva       medida 0.00072 vs teórica 0.00125 (mm/pieza)
```

**Cómo leerlo:** los coeficientes deben parecerse a la teoría (mismo orden de
magnitud y mismo signo). Si salieran negativos o enormes, algo está mal en los
datos. El R² bajo es esperable: el ruido de medición domina.

---

## Paso 7 — Decisiones operativas

```powershell
python ml\predecir_interactivo.py --ultimas 15
```

```
pieza      desgaste   riesgo   decisión
CIL-001         298    95.1%   CAMBIAR HERRAMIENTA
BASE-001        299    89.1%   CAMBIAR HERRAMIENTA
...
Riesgo medio             : 83.7 %
Piezas sobre el umbral   : 25

 ACCIÓN: cambiar la herramienta antes de seguir produciendo.
```

Las piezas de mayor desgaste deben recibir el riesgo más alto. Si no es así, el
modelo no está aprendiendo y hay que revisar los datos.

---

## Chequeo rápido de salud

Al terminar, estas cinco señales deben cumplirse:

| Señal | Valor sano |
|---|---|
| Las cuentas cuadran | `piezas = flujos × 7`, `mediciones = flujos × 82` |
| Tasa de defecto | 1 % – 8 % |
| Recall del modelo | > 50 % |
| Precisión del modelo | > 2× la tasa base |
| Riesgo en piezas de desgaste alto | claramente mayor que al inicio |

Si la tasa de defecto es plana frente al desgaste, el modelo no tendrá qué
aprender. Eso se corrige con el generador:

```powershell
python app\generador_datos.py --flujos 330 --deriva 3.0 --escala-defectos 0.05
```

---

## Ver los datos en Power BI

1. **Obtener datos → PostgreSQL**
2. Servidor `aws-0-us-east-2.pooler.supabase.com:5432`, base `postgres`
3. Usuario `powerbi_ro.<proyecto>` y su contraseña (está en `.env`)
4. Marca **usar conexión cifrada (SSL)**
5. Importa `v_entrenamiento_piezas` y `v_riesgo_piezas`

También se puede consultar por SQL:

```sql
SELECT COUNT(*), SUM(defectuosa) FROM public.v_entrenamiento_piezas;
SELECT * FROM calidad_piezas.vw_reporte_inspeccion LIMIT 20;
```

---

## Si algo falla

| Síntoma | Causa probable | Solución |
|---|---|---|
| `ModuleNotFoundError: conexion_supabase` | Ejecutaste un script de `ml/` desde otra carpeta | Usa `python ml\script.py` desde la raíz, o los `.bat` |
| `Faltan datos de conexión` | No existe `.env` | `python tools\configurar_bd.py` |
| `password authentication failed` | El rol cambió de clave | Repite `configurar_bd.py` y revisa `.env` |
| `La tabla 'v_riesgo_piezas' no existe` | No se crearon las vistas | `python tools\configurar_bd.py` |
| Métricas con 100 % de exactitud | El objetivo está invertido o hay fuga | Revisa que `DB_TARGET=defectuosa` |
| Recall muy bajo y precisión igual a la base | Los defectos son aleatorios | Genera con `--deriva 3.0 --escala-defectos 0.05` |

---

## Resumen de comandos

```powershell
cd "C:\Users\Edwin Quiroz\Salon106"

python -m pytest tests -q                                   # 1. pruebas
python tools\configurar_bd.py                               # 2. base
python app\generador_datos.py --flujos 20                   # 3. datos
python ml\entrenar_con_supabase.py --tabla v_riesgo_piezas  # 4. modelo
python ml\detectar_anomalias.py                             # 5. anomalías
python ml\regresion_cota.py --cota cota_bas_c01             # 6. regresión
python ml\predecir_interactivo.py --ultimas 15              # 7. decisiones
```
