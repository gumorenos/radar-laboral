# QA pendiente / ejecución en infraestructura

Este archivo registra pruebas que requieren Raspberry Pi, Cloudflare o el volumen persistente real. No sustituye las pruebas automatizadas ni los gates live ejecutados desde GitHub Actions.

## QA ya completado desde desarrollo

- Collector de El Peruano validado contra fuente real para `NL` + `EX`.
- Gate histórico **2026-08-01**: 124 `NL` + 16 `EX` = **140 dispositivos**.
- Consulta explícitamente vacía validada como éxito con 0, sin borrar catálogo.
- Gate live de visibilidad laboral **2026-07-22 a 2026-07-23**:
  - 146 documentos reales cargados a SQLite sin PDFs;
  - 3 `relevant`, 5 `review`, 138 `not_labor` con clasificador v3;
  - `DS 009-2026-TR` publicado el 2026-07-22 quedó `relevant / Teletrabajo`;
  - `RM 194-2026-TR` publicado en El Peruano el 2026-07-23 quedó `relevant / Inspección laboral`;
  - ambos controles aparecieron en la portada Flask con el default **Laborales + por revisar** y también con `Solo laborales relevantes`.
- Gate live de **cobertura diaria verificable**, ejecutado el 2026-08-24 contra los mismos dos días históricos:
  - 146 documentos reales cargados sin PDFs;
  - `2026-07-22`: 70 dispositivos, 2 relevantes, 2 por revisar, `is_complete=1`;
  - `2026-07-23`: 76 dispositivos, 1 relevante, 3 por revisar, `is_complete=1`;
  - la suma de `record_count` de `source_coverage_days` coincidió exactamente con los 146 documentos cargados;
  - `coverage_summary` para una ventana 2026-07-22 → 2026-07-23 devolvió `2/2`, `missing_days=0`, `100.0%`;
  - `/api/status`, portada y `/status` mostraron el mismo 100% usando fecha de referencia controlada;
  - el workflow live fue temporal y debe mantenerse fuera de `main` una vez cerrado el PR.
- Nota de calidad de fuente: la tarjeta oficial de El Peruano para `DS 009-2026-TR` reportó el emisor `SECRETARIA DEL CONSEJO DE MINISTROS`. Radar conserva ese metadato de origen y no lo reemplaza silenciosamente por una inferencia basada en el sufijo `-TR`; su clasificación laboral se sostiene por el contenido de Teletrabajo.
- SUNAFIL TFL tiene su gate live documentado en [`QA_TFL.md`](QA_TFL.md).
- La cola `sync_requests`, autenticación del POST, recuperación tras reinicio y worker histórico están cubiertos con SQLite temporal y mocks en CI.
- La semántica de cobertura está cubierta con tests: día vacío válido = completo; hoy = consultado pero abierto; fallo de fuente = no cobertura; el daemon cierra ayer una sola vez y continúa con hoy aunque ese cierre falle.
- El clasificador es versionado: una nueva versión fuerza reclasificación de filas antiguas al iniciar.

## 1. Despliegue del commit aprobado

Ejecutar únicamente después de que el PR correspondiente esté fusionado a `main`:

```bash
git switch main
git pull --ff-only
docker compose up -d --build
docker compose ps
```

Criterios:

- `radar-laboral` aparece `healthy`;
- `radar-laboral-sync` aparece `Up` sin healthcheck HTTP heredado;
- `radar-laboral-worker` aparece `Up` sin healthcheck HTTP heredado;
- no se pierde `storage/radar_laboral.db`, `storage/catalog/` ni `storage/pdfs/`.

## 2. Configuración segura de carga histórica web

El POST permanece deshabilitado mientras no exista `RADAR_ADMIN_TOKEN`. En el host, crear `.env` a partir de `.env.example` con un secreto largo y aleatorio. `.env` está ignorado por Git y no debe versionarse.

Variables relevantes:

```text
RADAR_ADMIN_TOKEN=<secreto-largo-y-aleatorio>
RADAR_MAX_BACKFILL_DAYS=366
RADAR_COVERAGE_DAYS=365
```

Tras recrear los contenedores, abrir `/status` y comprobar:

- selectores **Traer desde** y **Hasta** visibles y habilitados;
- **Traer desde** propone la primera fecha realmente faltante de la ventana de cobertura;
- campo de clave administrativa habilitado;
- el secreto real nunca aparece en HTML, `/api/status` ni logs normales;
- rango máximo indicado coincide con `RADAR_MAX_BACKFILL_DAYS`.

## 3. Cobertura diaria en el volumen persistente

Después del despliegue, `/status` debe mostrar **Cobertura diaria verificada**. En una instalación existente es esperado que inicialmente existan muchos días faltantes: Radar no convierte normas antiguas en cobertura por inferencia.

Criterios:

- la ventana termina ayer, no hoy;
- `/api/status` incluye `coverage.window_start`, `window_end`, `verified_days`, `missing_days`, `coverage_percent` y `missing_ranges`;
- hoy, si ya fue consultado, aparece como `today_checked` pero no incrementa `verified_days`;
- un backfill exitoso de días históricos reduce los huecos correspondientes;
- un fallo de fuente no marca ese día como completo.

Comprobación SQLite opcional:

```bash
docker compose exec -T radar-laboral python - <<'PY'
from radar_laboral.db import connect
with connect() as conn:
    rows = conn.execute(
        "SELECT coverage_date, record_count, is_complete, checked_at "
        "FROM source_coverage_days ORDER BY coverage_date DESC LIMIT 10"
    ).fetchall()
    for row in rows:
        print(dict(row))
PY
```

## 4. Carga histórica desde la UI

Primera prueba recomendada: **metadatos solamente**, usando la fecha sugerida por el propio indicador de cobertura.

Criterios:

- el POST responde con redirección a `/status`;
- aparece una fila `pending`, luego `running`, finalmente `success`;
- el navegador sigue respondiendo mientras el worker procesa;
- `/api/status` muestra la solicitud sin secretos;
- los días históricos procesados aparecen en `source_coverage_days`;
- la primera fecha faltante avanza cuando el rango cubre el hueco inicial;
- una solicitud idéntica mientras está activa no se duplica.

## 5. Visibilidad de normas laborales en Raspberry

La lógica ya pasó el gate real desde GitHub Actions. Después del backfill desplegado, confirmar además en el entorno persistente:

- la portada abre por defecto **Laborales + por revisar**;
- muestra filas `relevant` y `review`, pero no `not_labor`;
- el resumen superior informa relevantes, por revisar, inventario total y cobertura verificada;
- el filtro **Solo laborales relevantes** sigue disponible;
- la carga de un rango que incluya 22–23 de julio de 2026 permite localizar `009-2026-TR` y `194-2026-TR`.

## 6. Reinicio durante una carga

Con una solicitud suficientemente amplia en estado `running`, reiniciar solo `radar-laboral-worker`.

Criterios:

- al iniciar, el worker devuelve solicitudes `running` a `pending`;
- el rango vuelve a procesarse sin duplicar normas;
- finalmente la solicitud queda `success` o `failed` con error visible;
- la web permanece disponible.

La repetición es segura porque El Peruano se almacena por ID/OP con `upsert`.

## 7. Smoke del sincronizador diario y cierre de ayer

```bash
docker compose logs --tail=150 radar-laboral-sync
```

Criterios:

- al primer ciclo posterior al despliegue, si ayer no está completo, el daemon lo consulta antes de hoy;
- un cierre exitoso registra ayer como `is_complete=1`;
- los ciclos siguientes no vuelven a descargar ayer mientras siga completo;
- hoy se sigue consultando según el intervalo normal de 6 horas;
- si cerrar ayer falla, hoy se intenta igualmente;
- un vacío explícito válido termina como éxito con 0 y cuenta como cobertura histórica cuando la fecha ya cerró.

## 8. Repetición opcional del gate histórico ARM

```bash
docker compose run --rm radar-laboral \
  radar-laboral-backfill \
  --from 2026-08-01 \
  --to 2026-08-01 \
  --no-pdf
```

Criterio de referencia: **140 registros** = 124 `NL` + 16 `EX`. Además debe aparecer `2026-08-01` en `source_coverage_days` como completo. Si El Peruano modifica retrospectivamente ese día, conservar evidencia antes de actualizar el gate.

## 9. PDF real de una norma laboral

Después de metadatos, ejecutar un rango pequeño que contenga al menos una norma `relevant` o `review` con PDFs habilitados.

Criterios:

- solo se cachean PDFs para `relevant` / `review`;
- archivo comienza con `%PDF`;
- `sha256` queda informado;
- una segunda ejecución reutiliza el archivo cuando el hash coincide;
- un archivo corrupto se descarta y vuelve a descargar.

La cobertura diaria mide integridad de **metadatos de fuente**, no completitud de PDFs.

## 10. Smoke web / Cloudflare

Local:

```bash
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8080/api/status
```

Remoto: abrir el hostname de Cloudflare y comprobar portada, `/status`, `/jurisprudencia` y fichas. La acción administrativa solo debe funcionar con la clave correcta.

## 11. Daemon y worker

```bash
docker compose logs --tail=150 radar-laboral-sync
docker compose logs --tail=150 radar-laboral-worker
```

Criterios:

- daemon mantiene ciclos de 6 horas y el cierre idempotente de ayer;
- worker espera cuando la cola está vacía y procesa solicitudes al aparecer;
- fallos de fuente quedan registrados y no derriban permanentemente ninguno de los procesos.

## 12. Limpieza Git local: NO hacer automáticamente

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

Solo eliminar después de confirmar que no contienen personalizaciones no incorporadas a `main`.

## 13. Evidencia ante un fallo

No relajar validaciones de integridad para hacer pasar un collector. Guardar:

```bash
docker compose logs --tail=200 radar-laboral-sync
docker compose logs --tail=200 radar-laboral-worker
curl -s http://127.0.0.1:8080/api/status | python -m json.tool
```

Para backfill, conservar fecha, tipo de publicación (`NL`/`EX`), total oficial anunciado y cantidad de OP normalizados.
