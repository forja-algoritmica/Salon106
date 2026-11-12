# Linea de produccion automatizada con IA

Proyecto multidisciplinario: datos simulados -> rutina automatizada (ML) -> dashboard en Power BI.

## Estructura

| Carpeta | Contenido | Responsable |
|---|---|---|
| `app/` | Script de datos simulados (Python) | Equipo de datos |
| `ml/` | Rutina automatizada de ML (Python) | Equipo de ML |
| `network/` | Monitoreo de red, pruebas de firewall y logs | Ciberseguridad y redes |
| `docs/` | Diagrama, SQL de Supabase y tabla ISO 27001 | Todos |

## Arranque rapido

1. Crear las tablas y roles en Supabase (`docs/supabase_setup.sql`).
2. `cp .env.example .env` y llenar los datos de conexion (usuario `pipeline_rw`).
3. `docker compose up --build`
4. Plan B sin internet: `docker compose --profile local up --build` (con `DB_HOST=db_local` en `.env`).

Con el pooler de Supabase, el usuario suele tener el formato `usuario.ID_DEL_PROYECTO`; revisen su panel de conexion.

## Reglas del equipo

1. **Nunca** subir `.env`, llaves ni contrasenas a GitHub.
2. Las dependencias van en el `requirements.txt` de su carpeta, con versiones fijas cuando termine la etapa de pruebas.
3. El codigo lee host, puerto y credenciales **solo** desde variables de entorno.
4. Los contenedores corren sin root (ya esta resuelto en los Dockerfile).
5. Una rama por persona (`feature/nombre-tema`) y Pull Request antes de unir a `main`.
6. Power BI se conecta con el usuario `powerbi_ro` (solo lectura).
7. El enlace de Power BI se comparte solo con cuentas autorizadas, no publico.
