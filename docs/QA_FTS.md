# QA pendiente — búsqueda FTS5

La búsqueda de normas usa SQLite FTS5 cuando está disponible y conserva automáticamente el comportamiento anterior con `LIKE` cuando una compilación de SQLite no incluye FTS5. Por eso FTS5 es una optimización, no un requisito de despliegue.

Las pruebas automatizadas cubren creación/reconstrucción del índice, búsqueda por prefijo, búsqueda sin tildes, número de norma, filtros, actualización del índice después de `upsert` y fallback a `LIKE`.

## Verificación opcional en Raspberry Pi

Después de desplegar el commit que incorpore FTS5:

```bash
docker compose exec -T radar-laboral python - <<'PY'
from radar_laboral.db import connect, search_norms

with connect() as conn:
    enabled = bool(conn.execute("SELECT sqlite_compileoption_used('ENABLE_FTS5')").fetchone()[0])
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE name = 'norms_fts'"
    ).fetchone()

print("SQLite FTS5:", enabled)
print("Índice norms_fts:", bool(table))
print("Resultados teletra:", len(search_norms("teletra", relevance="all")))
PY
```

Criterios:

- si `SQLite FTS5: True`, debe existir `norms_fts`;
- una búsqueda por prefijo como `teletra` debe ejecutarse sin error;
- si `SQLite FTS5: False`, la aplicación debe seguir buscando con `LIKE` sin error ni migración manual;
- el primer arranque con FTS5 crea y reconstruye el índice de normas existentes; luego los triggers lo mantienen sincronizado.

Esta verificación no bloquea el despliegue si FTS5 no está compilado: el fallback es deliberado.
