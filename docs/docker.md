# Ejecución con Docker

> **Estado: no verificado.** El `docker-compose.yml` y los dos Dockerfile están
> escritos y revisados, pero **no se ejecutaron** en la máquina de desarrollo.
> Abajo se explica por qué y qué falta para probarlos.

## Por qué no se pudo ejecutar aquí

Docker Desktop necesita la característica de Windows **Virtual Machine Platform**
(y WSL2). En el equipo de desarrollo ocurrieron tres cosas:

1. La característica está deshabilitada y habilitarla requiere **permisos de
   administrador** y un **reinicio**.
2. La cuenta usada no tiene privilegios elevados:
   `Get-WindowsOptionalFeature` responde *"La operación solicitada requiere
   elevación"*.
3. La virtualización por hardware no está expuesta al sistema operativo:

   ```
   HypervisorPresent                        : True
   VirtualizationFirmwareEnabled            : False
   VMMonitorModeExtensions                  : False
   SecondLevelAddressTranslationExtensions  : False
   ```

   Eso ocurre cuando la máquina es ella misma una máquina virtual, o cuando la
   Seguridad Basada en Virtualización (VBS) ya está activa. Si es el primer caso,
   habilitar la característica no alcanzaría.

Además, esta máquina tiene políticas **WDAC** que ya bloquearon las extensiones
compiladas de numpy, pandas, SQLAlchemy y psycopg. Es probable que también
interfieran con los binarios de Docker.

## Qué se validó de forma estática

| Elemento | Verificación |
|---|---|
| `docker-compose.yml` | YAML válido: servicios `generador`, `ml`, `db_local`; volúmenes `pgdata_local` y `artefactos_ml` |
| `app/Dockerfile` | Copia el paquete `simulador`, `requirements.txt` y `config/`; usuario sin root (uid 10001) |
| `ml/Dockerfile` | Copia todos los scripts y ejecuta `rutina_ml.py`, que sí existe |
| Sistema de archivos de solo lectura | Corregido: los artefactos del ML van al volumen `artefactos_ml` vía `ML_DIR_ARTEFACTOS=/artefactos` |
| Dependencias | `numpy` y `pg8000` en ambos servicios (Python puro, sin DLL) |

## Requisitos para ejecutarlo en otra máquina

1. Windows 10/11 con virtualización habilitada en la BIOS/UEFI.
2. PowerShell **como administrador**:

   ```powershell
   Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -All -NoRestart
   wsl --install
   ```

3. Reiniciar el equipo.
4. Instalar Docker Desktop (opción *All-users installation* si la cuenta no es
   administradora).
5. Verificar que el servidor responde, no solo el cliente:

   ```powershell
   docker version
   docker compose version
   ```

## Comandos

```powershell
cd Salon106

# Producción: escribe en Supabase
docker compose up --build
docker compose logs -f generador
docker compose logs -f ml

# Detener
docker compose down
```

### Plan B sin internet (Postgres local)

En el `.env`:

```env
DB_HOST=db_local
DB_PORT=5432
DB_USER=pipeline_rw
DB_PASSWORD=CAMBIAR_CLAVE_PIPELINE_RW
DB_SSLMODE=disable
```

```powershell
docker compose --profile local up --build
```

`docs/supabase_setup.sql` se ejecuta automáticamente como script de
inicialización del contenedor `db_local`: crea el esquema, las tablas, el
trigger, los roles y las vistas. La clave `CAMBIAR_CLAVE_PIPELINE_RW` es un
marcador del archivo SQL; no es un secreto real.

## Qué esperar al arrancar

| Servicio | Comportamiento |
|---|---|
| `generador` | Flujos continuos, uno cada ~1 s, insertando en `calidad_piezas` |
| `ml` | Entrena si no hay modelo en el volumen; luego predice cada `INTERVALO_ML_SEGUNDOS` (600 s por defecto) |

Los artefactos del modelo quedan en el volumen `artefactos_ml`, no dentro del
contenedor, para que sobrevivan a los reinicios.

## Alternativa sin Docker

Todo el pipeline funciona de forma nativa en Windows, que es como se validó:

```powershell
python tools\configurar_bd.py
python app\generador_datos.py
python ml\entrenar_con_supabase.py --tabla v_riesgo_piezas
python ml\predecir_interactivo.py
python -m pytest tests -q
```
