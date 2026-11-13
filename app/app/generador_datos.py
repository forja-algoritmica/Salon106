"""Genera datos simulados de la linea de produccion y los inserta en PostgreSQL.

Es el servicio `generador` del docker-compose: corre la línea de ensamble de
forma continua y escribe en el esquema `calidad_piezas` de Supabase.

La configuración vive en `config/`:
    catalogo_cotas.csv  piezas, cotas, nominales y tolerancias
    proceso.json        ritmo, desgaste de herramienta y causas de defecto

Las credenciales llegan por variables de entorno (`DB_*`), definidas en el
archivo `.env` de la raíz del repositorio.
"""

import sys

from simulador.cli_linea import main

if __name__ == "__main__":
    sys.exit(main())
