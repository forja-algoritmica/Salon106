# Propuestas de ML en el repositorio: comparación y decisión pendiente

Documento para resolver, en equipo, cuál implementación de machine learning
queda en `main`. Hoy conviven tres propuestas distintas en las ramas y **no hay
ningún Pull Request abierto**, así que la decisión todavía no se ha tomado de
forma explícita.

Estado de las ramas al momento de escribir esto:

```
origin/main                        implementación base (esqueleto)
origin/adan                        borra ml/ y deja un stub
origin/feature/network-security    igual que adan + cambios de compose
origin/juliette                    mejora entrenar_con_supabase.py
origin/ricardo                     idéntica a main
```

---

## Propuesta A — implementación actual (árbol de trabajo sobre `main`)

**Modelo de datos:** esquema `calidad_piezas` con `revisiones_piezas`,
`mediciones_detalle` y `cotas_definicion`, más dos vistas en `public`
(`v_entrenamiento_piezas`, `v_riesgo_piezas`).

**Stack:** `numpy` + `pg8000` (Python puro, sin extensiones compiladas).

**Qué incluye:**

- Generador de la línea de ensamble (7 piezas, 82 cotas) que escribe en Supabase.
- Clasificación de riesgo con red neuronal.
- Decisiones operativas (continuar / revisar / cambiar herramienta).
- Detección de anomalías sin etiquetas.
- Regresión del valor de una cota.
- 17 pruebas automáticas + 27 del generador.

**Estado:** funciona de punta a punta. 2 331 piezas generadas, 68 defectuosas
(2,92 %). Recall 71,4 % sobre el conjunto de prueba.

**Riesgo de integrar:** ninguno técnico; es la única que corre hoy.

---

## Propuesta B — `adan` y `feature/network-security`

**Qué hace:** elimina `ml/README.md`, `conexion_supabase.py`,
`entrenar_con_supabase.py`, `predecir_interactivo.py` y `red_neuronal_ia.py`, y
deja un `ml/rutina_ml.py` de cinco líneas con instrucciones:

```python
# Equipo de ML: implementar aqui la rutina automatizada.
# - Leer de la tabla lecturas_linea y escribir en predicciones
#   (ver docs/supabase_setup.sql).
```

**Modelo de datos propuesto:** una tabla `lecturas_linea` de entrada y una tabla
`predicciones` de salida.

**Ventaja conceptual:** es un contrato muy claro y desacoplado. El generador no
necesita saber nada del ML: deja lecturas y recoge predicciones.

**Problema:** **ninguna de las dos tablas existe.** No están en
`docs/supabase_setup.sql` (que en `main` estaba vacío) ni en el esquema
`calidad_piezas`. Tampoco hay código que las cree, las llene o las lea. Es un
diseño enunciado, no implementado.

---

## Propuesta C — `juliette`

**Qué hace:** mantiene el pipeline de `main` y mejora un solo archivo,
`ml/entrenar_con_supabase.py` (+201 / −45):

- `seleccionar_columna_target`: valida que la columna objetivo configurada
  exista, en vez de caer silenciosamente en la última columna.
- `dividir_estratificado`: reparte por clase para que entrenamiento y prueba
  conserven ambas.
- `codificar_target_prueba`: aplica al conjunto de prueba la misma codificación
  que al de entrenamiento, y exige exactamente dos clases.

**Calidad:** las tres ideas son correctas y atacan problemas reales (fuga de
información y desbalance).

**Limitación:** sigue con `pandas` y sigue leyendo una tabla ancha de `public`
que no existe. Mejora la capa de entrenamiento, pero no resuelve de dónde salen
los datos ni cómo se conecta con el generador.

---

## Comparación

| Criterio | A (actual) | B (`adan`, `network`) | C (`juliette`) |
|---|---|---|---|
| Modelo de datos | `calidad_piezas` + vistas | `lecturas_linea` / `predicciones` (no existen) | tabla ancha en `public` (no existe) |
| ¿Corre hoy? | **Sí** | No | No, falta la tabla |
| Dependencias | numpy + pg8000 (funciona con WDAC) | sin definir | pandas (bloqueado en este equipo) |
| Cobertura | generador + ML + decisiones + pruebas | ninguna implementación | solo entrenamiento |
| Archivos que toca | 15 modificados, 8 nuevos | borra 5 de `ml/` | 1 |
| Al fusionar | — | conflicto de borrado en 5 archivos | conflicto en 1 archivo |

---

## Recomendación

**1. Adoptar A como base.** Es la única que produce datos, entrena, decide y
está probada. Las otras dos son propuestas parciales.

**2. Absorber C sin conflicto.** Sus tres ideas ya están implementadas en A
(validación del objetivo, división estratificada y codificación consistente).
Al resolver el conflicto de ese archivo hay que conservar su intención, no su
código literal.

**3. Resolver B con una capa de compatibilidad, no reescribiendo todo.**

En vez de elegir entre un modelo y otro, se pueden crear en `public` las dos
vistas con los nombres que B espera:

```sql
-- Una fila por lectura, tal como las produce el generador
CREATE VIEW public.lecturas_linea AS
SELECT r.id_revision, r.numero_serie_pieza, p.codigo_pieza,
       c.codigo_cota, m.valor_medido, m.es_conforme, r.fecha_revision
FROM calidad_piezas.mediciones_detalle m
JOIN calidad_piezas.revisiones_piezas r ON r.id_revision = m.id_revision
JOIN calidad_piezas.cotas_definicion c ON c.id_cota = m.id_cota
JOIN calidad_piezas.piezas p ON p.id_pieza = r.id_pieza;

-- Tabla de salida del modelo
CREATE TABLE public.predicciones (
    id_prediccion     SERIAL PRIMARY KEY,
    id_revision       INT,
    probabilidad      NUMERIC(6,4),
    decision          VARCHAR(30),
    modelo            VARCHAR(60),
    generado_en       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Así el `rutina_ml.py` de B encuentra exactamente lo que su comentario pide, sin
borrar nada de lo que ya funciona. Es la salida que menos trabajo cuesta y no
obliga a nadie a rehacer su parte.

---

## Preguntas que hay que cerrar en la reunión

1. **¿`lecturas_linea` es una fila por lectura (82 por ensamble) o una fila por
   pieza?** Cambia por completo el preprocesamiento.
2. **¿Quién escribe `predicciones`?** ¿La rutina de ML en cada ciclo, o el
   generador con lo que el modelo le devuelva?
3. **¿Se acepta `pandas` en el entregable?** En el equipo de desarrollo está
   bloqueado por políticas de seguridad (WDAC), así que un entregable basado en
   pandas no se puede ni ejecutar ni demostrar ahí.
4. **¿Quién es el dueño de `ml/`?** Hay dos personas modificando el mismo
   archivo en paralelo.
5. **¿El esquema definitivo es `calidad_piezas` o `public`?** Hoy el generador
   escribe en `calidad_piezas` y el ML lee vistas de `public`; conviene que sea
   una decisión consciente y documentada.

---

## Cómo verificar cualquiera de las propuestas

```powershell
python -m pytest tests -q                     # 17 pruebas, sin base de datos
python tools\configurar_bd.py                 # tablas, roles, vistas
python app\generador_datos.py --flujos 5      # produce datos
python ml\entrenar_con_supabase.py --tabla v_riesgo_piezas
python ml\predecir_interactivo.py
```

Si una propuesta no pasa esos cinco comandos, no está lista para `main`.
