# Diagrama de red

```mermaid
flowchart TD
    ADM[Administrador] -- Administracion local --> FW
    subgraph RED[Tu red]
        APP[Zona de aplicacion: Script + ML] --> FW[Firewall]
    end
    FW -- Conexion TLS prevista; filtrado pendiente --> SB[(Supabase PostgreSQL con RLS)]
    PBI[Power BI Service] -- lee --> SB
    USR[Usuarios] -- enlace --> PBI
```
