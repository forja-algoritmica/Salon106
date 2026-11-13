# Prompt para generar la presentación comercial

> Copia este documento completo y úsalo como instrucción para el modelo que
> escribirá la presentación. Está pensado para vender el proyecto, no para
> explicarlo técnicamente.

---

## Tu rol

Eres director creativo y guionista de presentaciones. Escribes para convencer,
no para explicar. Tu trabajo es que alguien sin conocimientos técnicos entienda
el valor del proyecto en los primeros treinta segundos y quiera saber más.

## El encargo

Escribe el contenido de una presentación de **9 diapositivas** para presentar
este proyecto como si fuéramos a venderlo. Duración objetivo: **5 minutos**.

## A quién le hablas

Un jurado o un decisor que **no es ingeniero**. Le importan tres cosas: que el
problema sea real, que la solución sea simple de entender y que el resultado se
pueda medir. No le importa cómo está programado.

## Reglas de escritura

1. **Cero tecnicismos.** Prohibidas palabras como: algoritmo, machine learning,
   red neuronal, API, esquema, trigger, backend, pipeline, Cpk, sigma, recall,
   precisión, numpy.
2. **Máximo 3 ideas por diapositiva.** Nunca un párrafo.
3. **Máximo 12 palabras por idea.** Si no cabe, se recorta.
4. **Título de 6 palabras o menos.**
5. Frases afirmativas, en voz activa, en presente.
6. Números redondeados y en lenguaje llano: "7 de cada 10", no "71,4 %".
7. Una idea por diapositiva. Si hay dos, son dos diapositivas.
8. Nada de siglas sin explicar en la misma línea.

## Reglas de contenido

- Habla siempre de **beneficios**, no de funciones.
- **Prohibido** mencionar limitaciones, riesgos, pendientes, lo que falta, lo
  que no hace, comparaciones con la competencia o disculpas.
- No inventes cifras. Usa solo las del apartado "Material de partida".
- No prometas resultados en plantas reales: presenta las cifras como
  **resultados de las pruebas del prototipo**.
- El cierre debe pedir algo concreto y fácil de conceder.

## Reglas de diseño (si generas el archivo)

- Estética elegante y sobria: mucho espacio en blanco, una sola idea visual por
  diapositiva.
- Máximo dos colores más el fondo. Sin degradados ni sombras.
- Título grande, subtítulo corto, tres líneas de apoyo como máximo.
- Sin tablas densas, sin capturas de código, sin diagramas con más de cinco
  cajas.
- Tipografía de un solo tipo, dos tamaños.
- Cada diapositiva debe entenderse sin que nadie la explique.

## Material de partida

Estos son los hechos. No agregues otros.

**El producto**
- Es un sistema de control de calidad para el ensamble de un brazo de
  retroexcavadora.
- El ensamble tiene 7 piezas y 82 puntos de control dimensionales.
- Hoy, cuando una pieza sale mal, ya está fabricada: solo queda desecharla o
  rehacerla.
- El sistema avisa del riesgo **antes** de que la pieza salga mal.
- Convierte ese aviso en tres acciones claras: continuar, revisar la pieza o
  cambiar la herramienta.
- Funciona sobre la base de datos que el taller ya tiene; no obliga a cambiar
  el proceso.
- Entrega un tablero para que el turno vea el estado en tiempo real.
- Puede empezar a aprender **antes** de instalar sensores, con datos simulados
  del propio producto.
- Encuentra piezas raras incluso cuando el taller nunca registró un rechazo.

**Resultados de las pruebas del prototipo**
- Detecta 7 de cada 10 piezas que habrían fallado.
- Es 5 veces mejor que decidir al azar.
- Encuentra piezas atípicas sin necesidad de histórico.
- Más de 40 pruebas automáticas confirman que funciona de punta a punta.
- Ya procesó más de 2.300 piezas y 42.000 mediciones.

**El costo**
- Menos de lo que cuesta una sola pieza rechazada al mes.
- Sin servidores propios ni instalaciones especiales.

**Lo que se pide al cierre**
- Acceso a los datos del taller para validar el sistema con piezas reales.

## Estructura de las diapositivas

| # | Diapositiva | Qué debe lograr |
|---|---|---|
| 1 | Portada | Una frase que intrigue y diga de qué se trata |
| 2 | El problema | Que el jurado sienta la pérdida de dinero |
| 3 | La idea | Explicar la solución en una sola frase |
| 4 | Cómo funciona | Tres pasos, sin tecnicismos |
| 5 | En el día a día | Qué cambia para el operador y para el jefe de turno |
| 6 | Los resultados | Las cifras, en lenguaje llano |
| 7 | Lo que cuesta | Costo pequeño frente al problema |
| 8 | Por qué este equipo | Confianza: ya está construido y probado |
| 9 | Cierre | La petición concreta |

## Formato de salida

Para cada diapositiva entrega:

```
DIAPOSITIVA N — [título de 6 palabras o menos]
Frase de apoyo: [una línea, máximo 15 palabras]
Ideas: 
 • [máximo 12 palabras]
 • [máximo 12 palabras]
 • [máximo 12 palabras]
Nota del presentador: [qué decir en voz alta, máximo 40 palabras]
```

Al final, agrega **una frase de apertura** para decir antes de la diapositiva 1
y **una frase de cierre** para después de la 9.

## Ejemplos de traducción

Así se pasa de lo técnico a lo comercial:

| ❌ No escribir | ✅ Escribir |
|---|---|
| "Recall del 71,4 %" | "Detecta 7 de cada 10 piezas que fallarían" |
| "Modelo supervisado sobre covariables" | "Avisa antes de que la pieza salga mal" |
| "Precisión 14,5 % frente a una base de 2,9 %" | "Es 5 veces mejor que decidir al azar" |
| "Esquema calidad_piezas con trigger" | "Usa la base que el taller ya tiene" |
| "Detección de anomalías no supervisada" | "Encuentra piezas raras sin histórico" |
| "82 cotas dimensionales" | "82 puntos de control por ensamble" |
| "44 pruebas automáticas" | "Más de 40 pruebas confirman que funciona" |

## Antes de entregar, verifica

- [ ] Ninguna diapositiva tiene más de 3 ideas.
- [ ] Ninguna idea supera 12 palabras.
- [ ] No aparece ninguna palabra de la lista prohibida.
- [ ] No hay ninguna mención a limitaciones, riesgos o pendientes.
- [ ] Todas las cifras provienen del material de partida.
- [ ] Cada diapositiva se entiende sola, sin explicación.
- [ ] El cierre pide algo concreto.
