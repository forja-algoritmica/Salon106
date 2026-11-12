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

## 4. Pruebas realizadas

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
| Pruebas con nmap | Pendiente | No realizadas |

Las pruebas de bloqueo se realizaron manualmente y la regla temporal fue eliminada después de la verificación.

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
