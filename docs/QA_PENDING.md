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
  - ambos controles aparecieron en la portada Flask con el default **Laborales + por revisar** y también con `Solo laborales relevantes`;
  - `/api/status` reportó cobertura `2026-07-22` → `2026-07-23`.
- Nota de calidad de fuente: la tarjeta oficial de El Peruano para `DS 009-2026-TR` reportó el emisor `SECRETARIA DEL CONSEJO DE MINISTROS`. Radar conserva ese metadato de origen y no lo reemplaza silenciosamente por una inferencia basada en el sufijo `-TR`; su clasificación laboral se sostiene por el contenido de Teletrabajo.
- SUNAFIL TFL tiene su gate live documentado en [`QA_TFL.md`](QA_TFL.md).
- La cola `sync_requests`, autenticación del POST, recuperación tras reinicio y worker histórico están cubiertos con SQLite temporal y mocks en CI.
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

Tras recrear los contenedores, abrir `/status` y comprobar:

- selectores **Traer desde** y **Hasta** visibles y habilitados;
- campo de clave administrativa habilitado;
- el secreto real nunca aparece en HTML, `/api/status` ni logs normales;
- rango máximo indicado coincide con `RADAR_MAX_BACKFILL_DAYS`.

## 3. Carga histórica desde la UI

Primera prueba recomendada: **metadatos solamente**, por ejemplo desde `2026-07-01` hasta la fecha actual.

Criterios:

- el POST responde con redirección a `/status`;
- aparece una fila `pending`, luego `running`, finalmente `success`;
- el navegador sigue respondiendo mientras el worker procesa;
- `/api/status` muestra la solicitud sin secretos;
- la primera fecha cargada retrocede al rango solicitado;
- una solicitud idéntica mientras está activa no se duplica.

## 4. Visibilidad de normas laborales en Raspberry

La lógica ya pasó el gate real desde GitHub Actions. Después del backfill desplegado, confirmar además en el entorno persistente:

- la portada abre por defecto **Laborales + por revisar**;
- muestra filas `relevant` y `review`, pero no `not_labor`;
- el resumen superior informa relevantes, por revisar, inventario total y cobertura temporal;
- el filtro **Solo laborales relevantes** sigue disponible;
- la carga de un rango que incluya 22–23 de julio de 2026 permite localizar `009-2026-TR` y `194-2026-TR`.

## 5. Reinicio durante una carga

Con una solicitud suficientemente amplia en estado `running`, reiniciar solo `radar-laboral-worker`.

Criterios:

- al iniciar, el worker devuelve solicitudes `running` a `pending`;
- el rango vuelve a procesarse sin duplicar normas;
- finalmente la solicitud queda `success` o `failed` con error visible;
- la web permanece disponible.

La repetición es segura porque El Peruano se almacena por ID/OP con `upsert`.

## 6. Smoke del sincronizador diario

```bash
docker compose run --rm radar-laboral radar-laboral-sync --no-pdf
```

Criterios:

- termina sin excepción;
- usa la fecha local de Lima;
- total oficial y cantidad normalizada coinciden;
- un vacío explícito termina como éxito con 0;
- `/api/status` registra la ejecución.

## 7. Repetición opcional del gate histórico ARM

```bash
docker compose run --rm radar-laboral \
  radar-laboral-backfill \
  --from 2026-08-01 \
  --to 2026-08-01 \
  --no-pdf
```

Criterio de referencia: **140 registros** = 124 `NL` + 16 `EX`. Si El Peruano modifica retrospectivamente ese día, conservar evidencia antes de actualizar el gate.

## 8. PDF real de una norma laboral

Después de metadatos, ejecutar un rango pequeño que contenga al menos una norma `relevant` o `review` con PDFs habilitados.

Criterios:

- solo se cachean PDFs para `relevant` / `review`;
- archivo comienza con `%PDF`;
- `sha256` queda informado;
- una segunda ejecución reutiliza el archivo cuando el hash coincide;
- un archivo corrupto se descarta y vuelve a descargar.

## 9. Smoke web / Cloudflare

Local:

```bash
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8080/api/status
```

Remoto: abrir el hostname de Cloudflare y comprobar portada, `/status`, `/jurisprudencia` y fichas. La acción administrativa solo debe funcionar con la clave correcta.

## 10. Daemon y worker

```bash
docker compose logs --tail=150 radar-laboral-sync
docker compose logs --tail=150 radar-laboral-worker
```

Criterios:

- daemon mantiene ciclos de 6 horas;
- worker espera cuando la cola está vacía y procesa solicitudes al aparecer;
- fallos de fuente quedan registrados y no derriban permanentemente el worker.

## 11. Limpieza Git local: NO hacer automáticamente

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

## 12. Evidencia ante un fallo

No relajar validaciones de integridad para hacer pasar un collector. Guardar:

```bash
docker compose logs --tail=200 radar-laboral-sync
docker compose logs --tail=200 radar-laboral-worker
curl -s http://127.0.0.1:8080/api/status | python -m json.tool
```

Para backfill, conservar fecha, tipo de publicación (`NL`/`EX`), total oficial anunciado y cantidad de OP normalizados.
