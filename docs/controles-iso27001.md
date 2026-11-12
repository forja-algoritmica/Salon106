# Controles ISO/IEC 27001:2022 — Red y seguridad

## Objetivo

Documentar la implementación y verificación de medidas de seguridad relacionadas con los controles del Anexo A de ISO/IEC 27001:2022 para el proyecto de línea de producción automatizada con inteligencia artificial.

La siguiente tabla representa una evaluación interna del proyecto y no constituye una certificación ISO 27001.

## Matriz de controles

| Control | Implementación en el proyecto | Evidencia | Estado |
|---|---|---|---|
| A.5.15 / A.8.3 — Control de acceso | Roles de mínimo privilegio previstos en Supabase | Archivo `docs/supabase_setup.sql`; falta validar roles aplicados | Pendiente de validar |
| A.5.17 / A.8.5 — Información de autenticación | Variables de conexión separadas del código mediante `.env` | `.env.example` y `.gitignore`; falta comprobar credenciales reales | Parcial |
| A.5.19 / A.5.23 — Proveedores y nube | Uso de Supabase y Power BI | Arquitectura del proyecto; falta validar permisos y conexión | Pendiente de validar |
| A.8.20 / A.8.21 — Seguridad de redes y servicios | Cadena personalizada en `DOCKER-USER`, monitoreo y bloqueo puntual | `firewall.sh`, logs `LP-FW:` y prueba `REJECT` | Parcial |
| A.8.22 — Segregación de redes | Redes Docker `app_net` y `data_net`, esta última interna | `docker-compose.yml`, `docker network ls` | Parcial |
| A.8.24 — Uso de criptografía | Configuración `DB_SSLMODE=require` prevista para PostgreSQL | `.env.example`; falta comprobar conexión TLS real | Pendiente de validar |
| A.8.15 / A.8.16 — Registro y monitoreo | Logs del firewall y configuración de rotación de logs Docker | `journalctl`, contador iptables y `docker-compose.yml` | Parcial |
| A.8.9 — Gestión de configuración | Configuración Docker y scripts de firewall versionados en Git | Rama `feature/network-security`, `docker-compose.yml` y archivos `network/` | Parcial |
| A.8.4 / A.8.25 — Código y desarrollo seguro | Desarrollo mediante ramas Git | Rama `feature/network-security`; falta verificar revisiones y permisos | Parcial |
| A.8.8 — Vulnerabilidades técnicas | Revisión de dependencias mediante `pip-audit` propuesta | Reporte de auditoría pendiente | Pendiente |
| A.8.28 — Codificación segura | Uso previsto de consultas parametrizadas y credenciales externas | Revisión del código Python pendiente | Pendiente de validar |
| A.5.29 / A.5.30 — Continuidad | PostgreSQL local como alternativa mediante perfil Docker | Configuración `db_local`; prueba de recuperación pendiente | Pendiente de validar |

## Evidencias técnicas obtenidas

### E1. Conectividad desde Docker

Se ejecutó un contenedor temporal conectado a `linea-produccion_app_net`, estableciendo una conexión TCP hacia `1.1.1.1:443`.

Resultado: `Conexion exitosa`.

### E2. Monitoreo del firewall

Se aplicó `network/firewall.sh` y se verificó la existencia de la cadena `LINEA-PRODUCCION`.

Resultado: regla `LOG` activa, contador de 1 paquete y 60 bytes, y evento `LP-FW:` registrado en el kernel.

### E3. Prueba de bloqueo

Se agregó temporalmente una regla `REJECT` para impedir conexiones TCP hacia `1.1.1.1:443`.

Resultado: `ConnectionRefusedError`, con 1 paquete contabilizado en la regla.

La regla se retiró después de la prueba.

### E4. Reversión del firewall

Se ejecutó `network/firewall-reset.sh` y se verificaron las reglas de `DOCKER-USER`.

Resultado: eliminación de `LINEA-PRODUCCION`, conservando las reglas existentes de Docker y UFW.

### E5. Gestión de configuración

Se registraron cambios de endurecimiento de Docker en la rama `feature/network-security`, mediante el commit `3a151d0`.

Los scripts firewall.sh y firewall-reset.sh, junto con la documentación de seguridad, fueron incorporados al repositorio en la rama feature/network-security.

## Resultados generales

Las pruebas permitieron comprobar el funcionamiento del monitoreo, el rechazo de una conexión específica y la reversión de reglas del firewall.

No se ha demostrado todavía una política general de salida exclusiva hacia Supabase, ni la seguridad de extremo a extremo de la conexión PostgreSQL.

## Actividades pendientes

- Verificar conectividad real con Supabase.
- Implementar y probar una política restrictiva de salida.
- Comprobar permisos y roles de la base de datos.
- Validar los logs de los contenedores en ejecución.
- Ejecutar análisis de dependencias si el tiempo lo permite.
- Adjuntar capturas de las pruebas realizadas.

## Conclusión

La implementación permitió aplicar algunas medidas de seguridad y comprobar su funcionamiento mediante pruebas en un entorno Docker local. Se obtuvieron evidencias de monitoreo, bloqueo puntual y reversión de reglas.

Aunque se lograron avances en los controles relacionados con redes, registros y gestión de configuración, todavía existen medidas pendientes de validar antes de considerar completa la seguridad del proyecto.
