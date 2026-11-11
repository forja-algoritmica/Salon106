# Machine Learning e IA con Datos Reales de Supabase

El sistema está configurado para **conectarse directamente a tu base de datos PostgreSQL en Supabase**, inspeccionar las tablas que ya tienes creadas, preprocesar automáticamente las columnas reales y entrenar la Red Neuronal Artificial sobre tus datos originales.

---

## ⚙️ Configuración de Conexión

Abre el archivo [`.env`](file:///c:/Users/Epicorsi/Desktop/Machine%20learning/.env) y escribe la contraseña de tu base de datos:

```env
SUPABASE_HOST=aws-0-us-east-2.pooler.supabase.com
SUPABASE_PORT=5432
SUPABASE_DB=postgres
SUPABASE_USER=postgres.abyptuknrvoaadjxkaer
SUPABASE_PASSWORD=TU_CONTRASEÑA_AQUI

# (Opcional) Si quieres especificar una tabla o columna target exacta:
# SUPABASE_TABLE=nombre_de_tu_tabla
# SUPABASE_TARGET_COLUMN=columna_que_quieres_predecir
```

> Si dejas `SUPABASE_TABLE` vacío, el sistema detecta automáticamente la tabla que tengas en tu esquema `public`.

---

## 🚀 Cómo Ejecutar

1. **Inspeccionar y listar las tablas que tienes en Supabase**:
   ```powershell
   python conexion_supabase.py
   ```

2. **Entrenar la Inteligencia Artificial con los datos de tu tabla**:
   ```powershell
   python entrenar_con_supabase.py
   ```

---

## 🧠 ¿Qué hace el código con tus datos reales?

1. **Inspección automática**: Detecta tus columnas, tipos de datos y registros en Supabase.
2. **Preprocesamiento inteligente**:
   - Limpia valores nulos o vacíos (`NaN`).
   - Normaliza variables numéricas (Z-score).
   - Codifica variables categóricas o de texto mediante One-Hot Encoding.
   - Identifica la variable objetivo (*Target*) o te permite elegirla.
3. **Red Neuronal Artificial (Deep Learning)**:
   - Configura la capa de entrada adaptada exactamente al número de columnas de tu base de datos.
   - Aplica activación ReLU en capas ocultas y Sigmoide en la salida.
   - Realiza aprendizaje por *Backpropagation* y *Gradient Descent*.
   - Guarda el modelo resultante en `modelo_supabase_ia.npz`.

