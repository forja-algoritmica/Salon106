# Estado del repositorio: hallazgos y propuesta

Mensaje para compartir con el equipo antes de integrar.

---

Hola equipo. Antes de integrar revisé el estado de las ramas y quiero dejar por
escrito lo que encontré, con evidencia, para revisarlo juntos.

## 1. `main` tiene el proyecto duplicado dentro de `app/`

**Evidencia:** existe `app/app/` con 17 archivos (`app/app/simulador/`,
`app/app/config/`, `app/app/generador_datos.py`). No existe `app/simulador/`.
También aparecieron copias en `app/ml/`, `app/tests/`, `app/docs/`,
`app/tools/` y `app/network/`.

**Impacto:** `app/generador_datos.py` en `main` sigue siendo el stub de una
línea, y el código real está un nivel más abajo. Tal como está, el generador no
se puede ejecutar desde `main`.

**Origen probable:** los commits de sincronización copiaron el árbol completo
dentro de `app/` en lugar de integrar la rama.

## 2. Se versionaron artefactos del modelo

**Evidencia:** seis archivos binarios en el repositorio:
`modelo_supabase_ia.npz` y `.json` en la raíz, en `ml/` y en `app/`, más
`detector_anomalias.json`.

**Impacto:** son ~96 KB que cambian en cada entrenamiento. Generan ruido en cada
diff, conflictos innecesarios y no aportan nada al repositorio: se regeneran con
un comando. Deberían estar en `.gitignore`.

## 3. Las ramas quedaron desalineadas

| Rama | Adelante | Atrás | Observación |
|---|---|---|---|
| `main` | — | — | Avanzó 3 commits |
| `feature/integracion-de-flujo` | 3 | 3 | Implementación completa y probada |
| `juliette` | 1 | 3 | Su cambio en `entrenar_con_supabase.py` se solapa con la reescritura |
| `feature/network-security` | 4 | 4 | PR #1 abierto; solo toca red, docs y compose |
| `adan` | 0 | 4 | Sin cambios propios: su propuesta de borrar `ml/` ya no aplica |
| `ricardo` | 0 | 1 | Ya fusionada en el PR #2 |

## 4. Riesgo si se integra sin ordenar

- Un merge de `main` hacia la rama de integración traería **53 archivos
  duplicados** y conflictos por contenido idéntico en rutas distintas.
- Si algún conflicto se resuelve tomando la versión de `main`, **se pierde el
  pipeline de ML completo** sin que aparezca un error visible.

## Propuesta

1. **Abrir el PR de `feature/integracion-de-flujo`.** Es la versión limpia:
   estructura correcta, 44 pruebas en verde y documentación completa.
2. **Crear una rama de limpieza** que elimine `app/app/`, `app/ml/`,
   `app/tests/`, `app/docs/`, `app/tools/`, `app/network/` y los artefactos
   `.npz` / `.json`, y añada los patrones correspondientes a `.gitignore`.
3. **Revisar el PR #1 de red por separado.** No toca `ml/` ni `app/`, así que no
   compite con la integración.
4. **Acordar tres reglas:** una rama por tema, PR antes de tocar `main`, y no
   copiar carpetas entre niveles.

## Anexo: limitaciones del entorno (no son errores del equipo)

- **Docker no se pudo ejecutar:** requiere virtualización y permisos de
  administrador. El compose está escrito y validado en estructura.
- **Las políticas WDAC del equipo bloquean** pandas, scikit-learn, SQLAlchemy y
  psycopg. Por eso el pipeline usa numpy y pg8000, que son Python puro.

Nada de esto es irreversible: son archivos duplicados y artefactos que se
eliminan en una rama, sin tocar el trabajo de nadie.
