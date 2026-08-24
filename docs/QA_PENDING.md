# QA pendiente / ejecución en infraestructura

Este archivo registra pruebas que requieren la Raspberry Pi, acceso de red real a las fuentes oficiales o el despliegue con Cloudflare. No sustituye las pruebas automatizadas de CI.

## Estado de referencia

- `main` desplegado y verificado antes de este cambio: `5b2f9861bebc3411862e9bd8d7ef26a1c25a5b12`.
- El sincronizador diario ya usa el buscador oficial de El Peruano por fecha (`NL` + `EX`).
- Validaciones manuales ya realizadas desde la Raspberry:
  - 2026-07-29 `NL`: HTTP 200, `13 dispositivos encontrados`, 13 OP detectados.
  - 2026-08-23 `NL`: HTTP 200, 0 OP y `No hay resultados para mostrar`.
- Este branch añade el backfill histórico reutilizando exactamente el mismo parser y las mismas validaciones del collector diario.

## 1. Despliegue del commit aprobado

Ejecutar únicamente después de que el PR correspondiente esté fusionado a `main`:

```bash
git switch main
git pull --ff-only
docker compose up -d --build
docker compose ps
```

Criterios de aceptación:

- `radar-laboral` aparece `healthy`.
- `radar-laboral-sync` aparece `Up` y no hereda el healthcheck HTTP del servidor web.
- no se pierde `storage/radar_laboral.db`, `storage/catalog/` ni `storage/pdfs/`.

## 2. Día sin publicaciones

Verifica que un día oficialmente vacío sea éxito y no un falso fallo del parser:

```bash
docker compose run --rm radar-laboral \
  radar-laboral-sync --date 2026-08-23 --no-pdf
```

Esperado:

```text
El Peruano: 0 registros; 0 relevantes; 0 por revisar; 0 PDF almacenados.
```

Después:

```bash
curl -s http://127.0.0.1:8080/api/status | python -m json.tool
```

Criterio: la última ejecución correspondiente debe quedar `success`, no `failed`.

## 3. Gate de integración del backfill histórico

Fecha conocida: **2026-08-01**.

El buscador oficial informó previamente:

- `NL`: 124 dispositivos.
- `EX`: 16 dispositivos.
- total esperado: **140 dispositivos**.

Ejecutar primero sin PDF:

```bash
docker compose run --rm radar-laboral \
  radar-laboral-backfill \
  --from 2026-08-01 \
  --to 2026-08-01 \
  --no-pdf
```

Criterio de aceptación: el comando termina sin excepción de integridad y reporta **140 registros** antes de considerar su clasificación laboral.

Si El Peruano cambia retrospectivamente el histórico y el total oficial deja de ser 140, documentar la nueva cifra y conservar evidencia del resultado antes de modificar este gate.

## 4. Idempotencia real

Repetir exactamente el comando anterior una segunda vez.

Criterios:

- no aparecen duplicados por OP en SQLite;
- el total de filas de esos OP permanece estable;
- el catálogo JSONL sigue teniendo una sola entrada por `id`;
- `sync_runs` registra una nueva ejecución independiente.

## 5. Ediciones regular y extraordinaria

Comprobar en `storage/catalog/norms.jsonl` que los registros del backfill incluyan:

```json
{"edition": "regular"}
```

o:

```json
{"edition": "extraordinary"}
```

La persistencia de `edition` dentro de SQLite/UI debe verificarse por separado cuando se incorpore su migración de esquema; el catálogo JSONL ya conserva este metadato.

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
- un día vacío se registra como sincronización completada con 0 registros;
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

## 10. Qué hacer ante un fallo

No relajar las validaciones de integridad para hacer pasar el collector. Guardar:

```bash
docker compose logs --tail=200 radar-laboral-sync
curl -s http://127.0.0.1:8080/api/status | python -m json.tool
```

Si el fallo está en un backfill, guardar también fecha, `tipoPublicacion` (`NL`/`EX`), total oficial anunciado y cantidad de OP normalizados. Un cambio de HTML debe corregirse en parser/tests antes de aceptar datos parciales.
