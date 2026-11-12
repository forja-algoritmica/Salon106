# Diagrama de red

```mermaid
flowchart TD
    subgraph HOST["Host Linux / Docker"]
        subgraph APP["app_net - salida a internet"]
            GEN["Generador Python"]
            ML["Modulo ML"]
        end
        subgraph DATA["data_net - interna"]
            DB[("PostgreSQL local opcional")]
        end
        FW["DOCKER-USER / iptables - monitoreo IPv4"]
    end
    GEN --> FW
    ML --> FW
    GEN -.-> DB
    ML -.-> DB
    FW -->|"Conexion prevista; filtrado pendiente"| SB[("Supabase PostgreSQL - RLS por validar")]
    PBI["Power BI Service"] -.->|"Conexion por validar"| SB
    USR["Usuarios"] -.->|"Acceso previsto"| PBI
```

Nota: Generador y ML pertenecen a ambas redes Docker. Las conexiones punteadas representan servicios opcionales o pendientes de validar. El firewall del proyecto funciona en modo observacion cuando se activa; no restringe exclusivamente la salida hacia Supabase.
