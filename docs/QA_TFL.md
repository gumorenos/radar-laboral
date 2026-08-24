# QA pendiente — SUNAFIL Tribunal de Fiscalización Laboral

Este checklist cubre pruebas que requieren red real, PDFs oficiales o el volumen persistente de la Raspberry Pi. Las pruebas de parser/orquestación permanecen en CI.

## Gate live antes de merge

Debe ejecutarse desde GitHub Actions temporal o entorno equivalente con acceso a `gob.pe`, sin convertir la fuente externa en dependencia permanente del CI.

Fuente:

```text
https://www.gob.pe/institucion/sunafil/normas-legales/tipos/145-resolucion-de-sala-plena
```

Registro estable de control:

```text
Resolución de Sala Plena N.° 001-2025-SUNAFIL-TFL
https://www.gob.pe/institucion/sunafil/normas-legales/6556395-001-2025-sunafil-tfl
```

Criterios del gate:

- el listado reconoce el registro `sunafil-tfl:6556395`;
- número `001-2025-SUNAFIL-TFL`;
- fecha de publicación `2025-03-10`;
- el detalle conserva la sumilla oficial y encuentra un PDF oficial;
- `binding_level` se establece como `precedente administrativo de observancia obligatoria` porque la sumilla oficial contiene expresamente esa declaración;
- una resolución cuya sumilla no contenga lenguaje de obligatoriedad debe quedar con `binding_level = NULL`;
- el histórico completo devuelve al menos los 53 registros observados al crear el collector. No usar 53 como igualdad permanente: nuevas Resoluciones de Sala Plena incrementarán naturalmente el total.

Después del gate, eliminar el workflow temporal para no depender de SUNAFIL en cada PR.

## Smoke de metadatos en Raspberry

Después de fusionar y desplegar:

```bash
docker compose run --rm radar-laboral \
  radar-laboral-sync-tfl \
  --all-pages \
  --no-pdf
```

Criterios:

- termina sin excepción;
- `storage/catalog/case_law.jsonl` existe;
- SQLite contiene registros `sunafil-tfl:*`;
- `/jurisprudencia` muestra las resoluciones;
- la ficha `001-2025-SUNAFIL-TFL` muestra la fuente oficial y el nivel explícito de obligatoriedad;
- `sync_runs` registra `source = 'SUNAFIL TFL'`, `status = 'success'` y `records_seen > 0`.

## Idempotencia e incrementalidad

Ejecutar el comando anterior una segunda vez.

Criterios:

- no se duplican filas por `id`;
- el catálogo JSONL mantiene una sola entrada por `id`;
- los detalles ya completos se reutilizan y no necesitan volver a consultarse salvo `--refresh-details`;
- cada ejecución genera un nuevo `sync_runs` independiente.

Para comprobar relectura deliberada:

```bash
docker compose run --rm radar-laboral \
  radar-laboral-sync-tfl \
  --pages 1 \
  --no-pdf \
  --refresh-details
```

## PDF real

Primero limitar la prueba a una página:

```bash
docker compose run --rm radar-laboral \
  radar-laboral-sync-tfl \
  --pages 1
```

Criterios:

- los archivos quedan en `storage/pdfs/sunafil-tfl/<año>/`;
- comienzan con `%PDF`;
- `sha256` queda almacenado;
- una segunda ejecución reutiliza un PDF íntegro;
- si un PDF local se corrompe y su hash ya no coincide, el collector lo elimina y lo descarga nuevamente;
- una redirección fuera de dominios `*.gob.pe` no debe aceptarse como PDF oficial.

## UI

Comprobar:

```text
/jurisprudencia
/jurisprudencia/sunafil-tfl:6556395
```

Criterios:

- búsqueda y filtros funcionan;
- la ficha separa claramente jurisprudencia de normas;
- `binding_level` se presenta como dato almacenado, no como inferencia de la aplicación;
- enlaces de fuente/PDF abren el documento oficial;
- las relaciones con normas, cuando existan en `document_relations`, muestran dirección y tipo de relación.

## Daemon

El collector TFL **no debe añadirse todavía** al daemon de 6 horas hasta que el gate live y el smoke en Raspberry hayan pasado. Una vez estable, integrar preferentemente con una frecuencia menor que El Peruano o con una ejecución que procese solo la primera página, para evitar releer el histórico innecesariamente.
