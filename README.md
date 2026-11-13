# Linea de produccion automatizada con IA

Proyecto multidisciplinario: datos simulados -> rutina automatizada (ML) -> dashboard en Power BI.

## Manual del flujo completo

> **Archivo: [`docs/flujo-completo.md`](docs/flujo-completo.md)**
>
> Es el **manual paso a paso para ejecutar todo el flujo del proyecto**: pruebas,
> preparación de la base, generación de datos, entrenamiento del modelo,
> detección de anomalías, regresión de cotas y decisiones de mantenimiento.
>
> Cada paso incluye el comando exacto, la salida que debe aparecer y cómo
> interpretarla. **Si es tu primera vez con el proyecto, empieza por ese archivo.**

## Estructura

| Carpeta | Contenido | Responsable |
|---|---|---|
| `app/` | Generador de datos simulación + inserción en `calidad_piezas` (Python) | Equipo de datos |
| `ml/` | Pipeline de ML: riesgo de pieza defectuosa y decisiones (Python) | Equipo de ML |
| `network/` | Firewall, VPN y logs | Ciberseguridad y redes |
| `docs/` | Diagrama, SQL de Supabase y tabla ISO 27001 | Todos |

## Arranque rápido (sin Docker)

Es la forma recomendada y la que se probó de punta a punta.

```powershell
# 1. Crear tablas, roles, permisos y vistas + generar el .env
python tools\configurar_bd.py

# 2. Generar datos (línea de ensamble continua)
python app\generador_datos.py

# 3. Entrenar el modelo de riesgo
python ml\entrenar_con_supabase.py --tabla v_riesgo_piezas

# 4. Predecir y decidir
python ml\predecir_interactivo.py
```

Si prefieres empezar sin escribir `.env` a mano, `tools\configurar_bd.py` genera
uno con contraseñas aleatorias para `pipeline_rw` y `powerbi_ro`.

## Lanzadores con doble clic

No hace falta compilar nada ni generar un `.exe`. En equipos con políticas de
seguridad (WDAC) los ejecutables sin firma quedan bloqueados, así que se usan
archivos `.bat` que invocan Python directamente:

| Archivo | Qué hace |
|---|---|
| `Ejecutar generador.bat` | Arranca la línea de ensamble. Acepta `--flujos N`, `--sin-db`, `--reloj simulado`. |
| `Ejecutar ML.bat` | Entrena el modelo, detecta anomalías y muestra las decisiones de mantenimiento. |
| `Ejecutar pruebas.bat` | Corre las 17 pruebas y dice si pasaron. |

Los `.bat` cargan el `.env` del repositorio automáticamente, así que no hay que
exportar variables ni abrir una consola especial.

> Para el recorrido completo, paso por paso y con lo que debe salir en cada uno,
> ver el **manual del flujo completo**: [`docs/flujo-completo.md`](docs/flujo-completo.md).

## Docker (opcional, no verificado aquí)

El repositorio incluye `docker-compose.yml` y un Dockerfile por servicio. **No se
pudieron ejecutar en la máquina de desarrollo** porque requiere la característica
de Windows "Virtual Machine Platform", que necesita permisos de administrador y
un reinicio. El detalle completo, los requisitos y los comandos están en
[`docs/docker.md`](docs/docker.md).

## Estado de las piezas

| Servicio | Estado |
|---|---|
| `app/generador_datos.py` | Simula la línea de ensamble del brazo (7 piezas, 82 cotas) y escribe en `calidad_piezas`. |
| `ml/entrenar_con_supabase.py` | Red neuronal, división estratificada y umbral de decisión. |
| `ml/predecir_interactivo.py` | Decisiones: continuar / revisar / cambiar herramienta. |
| `ml/detectar_anomalias.py` | Detección sin etiquetas (piezas raras aunque cumplan tolerancia). |
| `ml/regresion_cota.py` | Predice el valor de una cota desde temperatura y desgaste. |
| `docs/supabase_setup.sql` | Completo: tablas, trigger, roles, permisos y vistas de ML. |
| `docker-compose.yml` | Escrito y validado en estructura; **no ejecutado** por falta de virtualización. Ver `docs/docker.md`. |
| `docs/propuestas-ml.md` | Comparación de las tres propuestas de ML en las ramas y decisión pendiente. |
| `docs/flujo-completo.md` | **Manual del flujo completo**: pasos, comandos, salidas esperadas e interpretación. |
| `docs/prompt-contexto.md` | **Prompt de contexto**: todo el proyecto en un documento para educar a otro modelo. |
| `network/` | Pendiente. |

## Limitaciones conocidas

1. **Docker no se pudo ejecutar.** Requiere "Virtual Machine Platform", que
   necesita administrador y reinicio. El compose y los Dockerfile están
   revisados, pero no probados en marcha. Detalle en `docs/docker.md`.
2. **La máquina tiene políticas WDAC** que bloquean extensiones compiladas
   (numpy, pandas, SQLAlchemy, psycopg). Por eso todo el ML usa `numpy` y
   `pg8000`, que son Python puro. Ventaja: también funciona dentro del
   contenedor Linux.
3. **El simulador necesita deriva para que el ML tenga señal.** Con la
   configuración realista (defectos aleatorios) la tasa es plana frente al
   desgaste y ningún modelo puede anticiparse. El perfil de
   `app/config/proceso.json` sube la deriva justamente para que haya algo que
   aprender. Ver `ml/README.md`.

## Cómo ejecutar las pruebas

```powershell
python -m pytest tests -q
```

No tocan la base de datos ni la red: son rápidas (~1 s) y se pueden correr sin
credenciales.

| Archivo | Qué comprueba |
|---|---|
| `tests/test_generador.py` | Que el catálogo tenga 7 piezas y 82 cotas, que cada corrida genere 7 piezas y 82 mediciones, reproducibilidad con la misma semilla, evaluación correcta contra tolerancias y que la deriva aumente la dispersión al final de la vida de la herramienta. |
| `tests/test_ml.py` | Preprocesamiento (numéricas, categóricas, alta cardinalidad), forma de salida de la red, aprendizaje de una función simple, división estratificada, sobremuestreo, elección de umbral, reglas de decisión, detección de una pieza extrema y recuperación de coeficientes en la regresión. |

Resultado esperado:

```
.................                                                        [100%]
17 passed in 0.20s
```

Si falta pytest:

```powershell
pip install pytest
```

Para correr solo una parte:

```powershell
python -m pytest tests/test_ml.py -q          # solo ML
python -m pytest tests -q -k anomalia         # solo pruebas de anomalías
```

Con el pooler de Supabase, el usuario suele tener el formato `usuario.ID_DEL_PROYECTO`; revisen su panel de conexion.

## Reglas del equipo

1. **Nunca** subir `.env`, llaves ni contrasenas a GitHub.
2. Las dependencias van en el `requirements.txt` de su carpeta, con versiones fijas cuando termine la etapa de pruebas.
3. El codigo lee host, puerto y credenciales **solo** desde variables de entorno.
4. Los contenedores corren sin root (ya esta resuelto en los Dockerfile).
5. Una rama por persona (`feature/nombre-tema`) y Pull Request antes de unir a `main`.
6. Power BI se conecta con el usuario `powerbi_ro` (solo lectura).
7. El enlace de Power BI se comparte solo con cuentas autorizadas, no publico.
