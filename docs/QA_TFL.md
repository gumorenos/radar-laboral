# QA — SUNAFIL Tribunal de Fiscalización Laboral

Este checklist separa el QA ya completado contra SUNAFIL real de las pruebas que todavía requieren el volumen persistente de la Raspberry Pi.

## QA live completado antes de merge

Fuente oficial:

```text
https://www.gob.pe/institucion/sunafil/normas-legales/tipos/145-resolucion-de-sala-plena
```

Registro estable de control:

```text
Resolución de Sala Plena N.° 001-2025-SUNAFIL-TFL
https://www.gob.pe/institucion/sunafil/normas-legales/6556395-001-2025-sunafil-tfl
```

Gate ejecutado en GitHub Actions temporal el 2026-08-24. Resultado:

- listado real: 53 resoluciones distribuidas en 25 + 25 + 3;
- paginación real: páginas 1 y 2 con siguiente, página 3 final;
- registro `sunafil-tfl:6556395` reconocido;
- número `001-2025-SUNAFIL-TFL`;
- fecha de publicación `2025-03-10`;
- sumilla oficial completa extraída desde el bloque `description rule-content` (527 caracteres en el control);
- `binding_level = precedente administrativo de observancia obligatoria` únicamente porque la sumilla oficial lo declara expresamente;
- PDF oficial descargado y validado con firma `%PDF`;
- tamaño observado del PDF de control: 957145 bytes;
- SHA-256 observado: `8960cfa1817e499775d60d599cc00e941dad879942bfacda186984e1eedef889`;
- una segunda llamada al cache reutilizó el PDF local sin hacer red.

El workflow temporal de QA live se eliminó después de este gate para que el CI normal no dependa de `gob.pe`. El head final sin ese workflow volvió a pasar unit tests, compilación, validación de Compose y build de contenedor.

No usar 53 como igualdad permanente: nuevas Resoluciones de Sala Plena incrementarán naturalmente el total.

## Smoke de metadatos en Raspberry — pendiente

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

## Idempotencia e incrementalidad en volumen persistente — pendiente

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

## PDF real en Raspberry — pendiente de entorno ARM/volumen

La lógica y un PDF real ya pasaron el gate de GitHub Actions. En Raspberry queda confirmar el volumen persistente:

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

## UI — pendiente de smoke desplegado

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

El collector TFL no se incorpora todavía al daemon de 6 horas. Primero debe pasar el smoke en Raspberry. Después conviene programarlo con una frecuencia menor que El Peruano y procesar por defecto solo la primera página para no releer el histórico innecesariamente.
