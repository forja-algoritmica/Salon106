# Seguridad de red — Línea de producción automatizada

## 1. Objetivo

Implementar y verificar medidas de seguridad para los contenedores Docker utilizados por el generador de datos y el módulo de inteligencia artificial.

## 2. Arquitectura de red

El proyecto utiliza dos redes Docker:

| Red | Subred | Función |
|---|---|---|
| `app_net` | `172.28.0.0/24` | Comunicación de los servicios de Python |
| `data_net` | Administrada por Docker | Red interna para servicios de datos |

La red `data_net` utiliza `internal: true`, lo que restringe su acceso directo a redes externas. Sin embargo, los servicios conectados simultáneamente a `app_net` pueden utilizar esta última para acceder al exterior.

Los servicios Python cuentan con medidas de endurecimiento como ejecución sin privilegios de root, sistema de archivos de solo lectura, eliminación de capacidades Linux, `no-new-privileges` y rotación de logs.

## 3. Firewall

Se utiliza iptables mediante la cadena `DOCKER-USER`, que permite inspeccionar tráfico reenviado por Docker antes de sus reglas habituales.

Archivos:

- `network/firewall.sh`: configura el monitoreo IPv4 de `app_net`.
- `network/firewall-reset.sh`: elimina las reglas personalizadas del proyecto.

### Activación

```bash
sudo ./network/firewall.sh
```

### Verificación

```bash
sudo iptables -L LINEA-PRODUCCION -n -v --line-numbers
sudo journalctl -k --since "5 minutes ago" | grep 'LP-FW'
```

### Reversión

```bash
sudo ./network/firewall-reset.sh
```

**Limitación:** el script actual solo registra conexiones IPv4 nuevas. No aplica todavía una política general de bloqueo ni limita la salida exclusivamente a Supabase.

### Notas de uso

- La red `linea-produccion_app_net` debe existir antes de ejecutar `firewall.sh`.
- Si Docker recrea la red y cambia su interfaz, ejecutar primero `firewall-reset.sh` y después `firewall.sh` para actualizar las reglas.
- El registro `LOG` utiliza `--limit 5/min --limit-burst 5` y solo registra conexiones IPv4 nuevas que atraviesan la regla. No es un registro exhaustivo de todo el tráfico.
- Las reglas personalizadas no tienen persistencia automática después de reiniciar el sistema.

## 4. Pruebas de seguridad y estado de validación

| Prueba | Resultado | Evidencia |
|---|---|---|
| Conectividad TCP desde `app_net` hacia `1.1.1.1:443` | Exitosa | Mensaje `Conexion exitosa` |
| Registro de conexiones con iptables | Exitosa | Contador de 1 paquete y 60 bytes |
| Registro del kernel | Exitosa | Evento `LP-FW:` en `journalctl` |
| Bloqueo temporal de `1.1.1.1:443` con `REJECT` | Exitosa | `ConnectionRefusedError` y contador de 1 paquete |
| Ejecución de `firewall.sh` | Exitosa | Cadena creada y conectada a `DOCKER-USER` |
| Ejecución de `firewall-reset.sh` | Exitosa | Cadena eliminada y reglas originales conservadas |
| Conectividad real con Supabase | Pendiente | Falta configurar `DB_HOST` |
| Restricción general de tráfico | Pendiente | Requiere política definitiva |
| Nmap desde Kali hacia app_net (172.28.0.2:8000) | Exitosa | Desde docker-labs_default: filtered; conectado a app_net: open |
| Nmap desde Kali hacia data_net (172.18.0.2:8000) | Exitosa | Desde docker-labs_default: filtered; conectado a data_net: open |

Las pruebas de bloqueo se realizaron manualmente y la regla temporal fue eliminada después de la verificación.

Los contadores de paquetes corresponden a ejecuciones puntuales de las pruebas y no representan estadísticas acumuladas del tráfico de red.

### Validación TLS con Supabase

- **E-SUP-01:** conexión TCP exitosa desde `app_net` hacia `aws-0-us-east-2.pooler.supabase.com:5432`.
- **E-SUP-02:** el servidor aceptó la solicitud PostgreSQL `SSLRequest`.
- **E-SUP-03:** negociación TLS 1.3 desde CachyOS con la CA de Supabase; `Verify return code: 0 (ok)`.
- **E-SUP-04:** negociación TLS 1.3 desde Docker con verificación de cadena y hostname; `Verification: OK`, `Verified peername: *.pooler.supabase.com` y cifrado `TLS_AES_256_GCM_SHA384`.

Estas pruebas no validan todavía la autenticación PostgreSQL, las políticas RLS ni la configuración TLS de los servicios `generador` y `ml`.

## 5. Logs

El firewall registra conexiones mediante el prefijo `LP-FW:`. Docker también dispone de configuración de rotación de logs con un tamaño máximo de 10 MB y tres archivos por contenedor para los servicios que utilizan la configuración común.

Los logs de los contenedores pueden consultarse con:

```bash
docker compose logs
```

La configuración de rotación existe, pero todavía no se ha validado con contenedores ejecutándose.

## 6. Limitaciones y pendientes

- Obtener el host y puerto reales de Supabase.
- Implementar y validar la restricción de salida autorizada.
- Revisar DNS, IPv6 y posibles cambios de dirección IP del proveedor.
- Validar el funcionamiento completo del generador y del módulo ML.
- Ejecutar pruebas adicionales con nmap si el tiempo lo permite.
- Guardar capturas o archivos de evidencia para la entrega.

WireGuard queda fuera del alcance actual porque no se ha definido un servidor ni una necesidad concreta de administración remota.

## 7. Conclusión

Se implementaron y probaron mecanismos de monitoreo, bloqueo puntual y reversión de reglas de firewall para la red Docker del proyecto. Las pruebas confirman el funcionamiento de estos mecanismos en el entorno local.

La restricción completa de acceso a Supabase permanece pendiente y no debe considerarse implementada hasta realizar pruebas con el servicio real.
