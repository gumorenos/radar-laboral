# QA pendiente / ejecución en infraestructura

Este archivo registra pruebas que requieren la Raspberry Pi, el despliegue con Cloudflare o verificación de archivos persistentes/PDF reales. No sustituye las pruebas automatizadas de CI.

## QA ya completado desde desarrollo

- `main` desplegado antes de este cambio: `5b2f9861bebc3411862e9bd8d7ef26a1c25a5b12`.
- El collector diario ya usa el buscador oficial de El Peruano por fecha (`NL` + `EX`).
- Validación web oficial del **2026-08-01**:
  - `NL`: 124 dispositivos;
  - `EX`: 16 dispositivos;
  - total: 140.
- Integración live ejecutada en GitHub Actions contra El Peruano real, run `32687133889`:
  - `radar-laboral-backfill --from 2026-08-01 --to 2026-08-01 --no-pdf` terminó con 140 registros;
  - SQLite quedó con 124 `edition=regular` y 16 `edition=extraordinary`;
  - `sync_runs` registró `success`, `records_seen=140`;
  - una consulta futura sin resultados (`2026-12-31`) se registró como `success`, `records_seen=0`.
- El workflow live fue temporal y se eliminó después del gate para que el CI normal no dependa de una fuente externa.
- Importante: el 2026-08-23 aparecía vacío durante la madrugada, pero más tarde El Peruano publicó 37 dispositivos. No usar una fecha de publicación en curso como fixture permanente de "día vacío".

## 1. Despliegue del commit aprobado

Ejecutar únicamente después de que el PR correspondiente esté fusionado a `main`:

```bash
git switch main
git pull --ff-only
docker compose up -d --build
docker compose ps
```

Criterios de aceptación:

- `radar-laboral` aparece `healthy`;
- `radar-laboral-sync` aparece `Up` y no hereda el healthcheck HTTP del servidor web;
- no se pierde `storage/radar_laboral.db`, `storage/catalog/` ni `storage/pdfs/`.

## 2. Smoke del sincronizador diario en Raspberry

```bash
docker compose run --rm radar-laboral radar-laboral-sync --no-pdf
```

No fijar un número esperado para la fecha en curso. El criterio es:

- termina sin excepción;
- respeta la fecha local de Lima;
- si El Peruano informa un total, la cantidad normalizada coincide;
- si El Peruano devuelve explícitamente `No hay resultados para mostrar`, termina como éxito con 0;
- `/api/status` registra la ejecución como `success`.

```bash
curl -s http://127.0.0.1:8080/api/status | python -m json.tool
```

## 3. Repetición opcional del gate histórico en Raspberry

El gate ya pasó contra la fuente real desde GitHub Actions. Para confirmar además el entorno ARM/Docker de la Raspberry:

```bash
docker compose run --rm radar-laboral \
  radar-laboral-backfill \
  --from 2026-08-01 \
  --to 2026-08-01 \
  --no-pdf
```

Criterio: **140 registros** = 124 `NL` + 16 `EX`.

Si El Peruano cambia retrospectivamente el histórico y el total oficial deja de ser 140, documentar la nueva cifra y conservar evidencia antes de modificar este gate.

## 4. Idempotencia real sobre el volumen persistente

Repetir exactamente el comando anterior una segunda vez.

Criterios:

- no aparecen duplicados por OP en SQLite;
- el total de filas de esos OP permanece estable;
- el catálogo JSONL sigue teniendo una sola entrada por `id`;
- `sync_runs` registra una nueva ejecución independiente.

La misma propiedad ya está cubierta con pruebas automatizadas sobre SQLite temporal; esta prueba confirma el volumen persistente real.

## 5. Migración y visualización de edición

Comprobar que la base existente recibió `edition` y conserva las ediciones extraordinarias:

```bash
docker compose exec -T radar-laboral python - <<'PY'
from radar_laboral.db import connect

with connect() as conn:
    columns = [row[1] for row in conn.execute("PRAGMA table_info(norms)")]
    print("edition column:", "edition" in columns)
    print(
        "extraordinary rows:",
        conn.execute("SELECT COUNT(*) FROM norms WHERE edition = 'extraordinary'").fetchone()[0],
    )
PY
```

Criterios:

- `edition column: True`;
- después de cargar 2026-08-01, el conteo extraordinario es al menos 16;
- `storage/catalog/norms.jsonl` también conserva `regular` / `extraordinary`;
- la interfaz web muestra la etiqueta **Extraordinaria** en esos registros.

## 6. PDF real de una norma laboral

Después de validar solo metadatos, ejecutar un rango pequeño que contenga al menos una norma clasificada `relevant` o `review`:

```bash
docker compose run --rm radar-laboral \
  radar-laboral-backfill \
  --from YYYY-MM-DD \
  --to YYYY-MM-DD
```

Criterios:

- solo se intenta cachear PDF para `relevant` / `review`;
- el archivo local comienza con `%PDF`;
- `sha256` queda informado;
- una segunda ejecución reutiliza el PDF cuando el hash coincide;
- si el archivo local se corrompe, una ejecución posterior debe descartarlo y volver a descargarlo.

## 7. Smoke test web / Cloudflare

Local:

```bash
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8080/api/status
```

Remoto: abrir el hostname configurado en Cloudflare Tunnel y comprobar que la vista principal y `/status` carguen correctamente.

## 8. Estado del daemon después del despliegue

```bash
docker compose logs --tail=150 radar-laboral-sync
```

Criterios:

- la primera sincronización se ejecuta tras el delay configurado;
- una respuesta vacía explícita se registra como sincronización completada con 0 registros;
- un HTML ambiguo o un total oficial que no coincide con los OP normalizados continúa siendo error visible.

## 9. Limpieza Git local: NO hacer automáticamente

La Raspberry conserva antecedentes de la migración inicial del clone:

- branch local antiguo `feat/initial-scaffold`;
- stash `pre-main-switch`;
- posible backup `compose.yaml.pre-deploy-20260822-232617` dentro del stash.

Antes de borrar nada:

```bash
git stash list
git stash show --stat stash@{0}
git branch -vv
```

Solo eliminar el stash/branch después de confirmar que no contienen ninguna personalización que no esté ya en `main`. No forma parte del despliegue normal.

## 10. Qué guardar ante un fallo

No relajar las validaciones de integridad para hacer pasar el collector. Guardar:

```bash
docker compose logs --tail=200 radar-laboral-sync
curl -s http://127.0.0.1:8080/api/status | python -m json.tool
```

Si el fallo está en un backfill, guardar también fecha, `tipoPublicacion` (`NL`/`EX`), total oficial anunciado y cantidad de OP normalizados. Un cambio de HTML debe corregirse en parser/tests antes de aceptar datos parciales.
