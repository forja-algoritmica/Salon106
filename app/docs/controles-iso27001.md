# Controles ISO/IEC 27001:2022 (Anexo A) - Parte de red y seguridad

Completar la columna de evidencia conforme se implemente cada control.

| Control | Descripcion | Implementacion en el proyecto | Evidencia | Estado |
|---|---|---|---|---|
| A.5.15 / A.8.3 | Control de acceso y restriccion de acceso a la informacion | Roles de minimo privilegio (pipeline_rw, powerbi_ro) y RLS en Supabase | Captura del SQL y de los roles | Pendiente |
| A.5.17 / A.8.5 | Informacion de autenticacion y autenticacion segura | Secretos en .env fuera de Git; VPN con llaves | .gitignore, .env.example | Pendiente |
| A.5.19 / A.5.23 | Proveedores y servicios en la nube | Uso de Supabase y Power BI; SSL obligatorio, enlace compartido solo con cuentas autorizadas | Configuracion de sharing y SSL | Pendiente |
| A.8.20 / A.8.21 | Seguridad de redes y de servicios de red | Redes Docker separadas, firewall con salida restringida | Reglas del firewall, pruebas con nmap | Pendiente |
| A.8.22 | Segregacion de redes | app_net (salida filtrada) y data_net (interna, sin internet) | docker network inspect | Pendiente |
| A.8.24 | Uso de criptografia | TLS hacia Supabase (sslmode=require) | Cadena de conexion y prueba | Pendiente |
| A.8.15 / A.8.16 | Registro y monitoreo | Logs de contenedores y del firewall | Salida de docker compose logs | Pendiente |
| A.8.9 | Gestion de la configuracion | Infraestructura como codigo en GitHub (docker-compose.yml) | Repositorio | Pendiente |
| A.8.4 / A.8.25 | Acceso al codigo y desarrollo seguro | GitHub con ramas y revision de cambios | Configuracion del repo | Pendiente |
| A.8.8 | Gestion de vulnerabilidades tecnicas | Versiones fijas y revision de dependencias (pip-audit) | Reporte de pip-audit | Pendiente |
| A.8.28 | Codificacion segura | Consultas parametrizadas, sin credenciales en el codigo | Revision de codigo | Pendiente |
| A.5.29 / A.5.30 | Continuidad | Plan B con PostgreSQL local (perfil local) | Prueba de arranque del perfil local | Pendiente |
