# Radar Laboral Perú

Repositorio ligero y autocontenido para **capturar, conservar y consultar normativa laboral peruana y jurisprudencia laboral**, con trazabilidad hacia la fuente oficial.

El objetivo del proyecto no es reemplazar a El Peruano, MTPE, SUNAFIL, el Tribunal Constitucional, el Poder Judicial u otras fuentes oficiales. La idea es mantener un repositorio local consultable con metadatos y copias de los documentos oficiales, de modo que cada instalación pueda investigar sin depender de un chat ni de inteligencia artificial.

## Principios

- **Fuente primero:** cada registro conserva URL oficial, URL del PDF y hash del archivo descargado cuando existe copia local.
- **Determinístico por defecto:** captura, almacenamiento, búsqueda y clasificación básica no requieren IA.
- **Ligero:** una aplicación Python, SQLite y una interfaz web simple.
- **Portable:** el mismo código debe correr en Linux, Docker y, más adelante, como ejecutable portable para Windows.
- **Reproducible:** los catálogos pueden exportarse/versionarse como texto; la base SQLite y los PDF se reconstruyen o descargan localmente.
- **Extensible:** conceptos, IA, búsqueda semántica y resúmenes pueden añadirse por capas sin convertirse en la fuente de verdad.

## Capas de contenido

Radar Laboral separa tres tipos de información:

1. **Normas:** leyes, decretos, resoluciones y otras disposiciones oficiales.
2. **Jurisprudencia:** sentencias, casaciones, precedentes y criterios administrativos relevantes, almacenados como un tipo de documento distinto.
3. **Conceptos:** explicaciones generales de materias laborales mantenidas como Markdown versionable y enlazadas a sus fuentes.

Ver [`docs/content-model.md`](docs/content-model.md) para el diseño de estas relaciones.

## Funcionalidad actual

1. Catálogo SQLite con metadatos normalizados.
2. Interfaz web para buscar, filtrar y paginar normas.
3. Biblioteca independiente de jurisprudencia con búsqueda, filtros, paginación y fichas.
4. Cache local de PDF oficiales con SHA-256.
5. Collector determinístico de El Peruano por fecha, incluyendo edición regular y extraordinaria.
6. Clasificación determinística de relevancia laboral.
7. Sincronización periódica, deduplicación y registro de ejecuciones.
8. Backfill histórico de El Peruano por rango de fechas.
9. Collector de Resoluciones de Sala Plena del Tribunal de Fiscalización Laboral de SUNAFIL.
10. Relaciones auditables entre normas y jurisprudencia.
11. Docker para servidor Linux.
12. Preparación para empaquetado portable en Windows.

## Arquitectura

```text
Fuentes oficiales
      |
      v
  collectors  ---> catálogos JSONL
      |                 |
      v                 v
 storage/pdfs/       SQLite local
      |                 |
      +-------> aplicación web
```

Ver [`docs/architecture.md`](docs/architecture.md) para las decisiones iniciales.

## Desarrollo local

Requiere Python 3.11 o superior.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
radar-laboral --open-browser
```

La aplicación usa por defecto `./storage/radar_laboral.db` y escucha en `http://127.0.0.1:8080`.

## Sincronizar El Peruano

Ejecución manual:

```bash
radar-laboral-sync
```

El comando consulta el buscador oficial de El Peruano para la fecha local de Lima, por separado para Normas Legales (`NL`) y Edición Extraordinaria (`EX`). Normaliza los dispositivos, exige que el total informado coincida con los OP reconocidos, clasifica su relevancia laboral, hace `upsert` en SQLite y actualiza el catálogo JSONL.

Un día que El Peruano marca explícitamente como `No hay resultados para mostrar` se considera una sincronización válida con cero novedades. En cambio, HTML ambiguo, paginación incompleta o un total que no coincide siguen siendo errores visibles.

Para consultar una fecha concreta o comprobar solo metadatos:

```bash
radar-laboral-sync --date 2026-08-23 --no-pdf
```

Cuando puede resolver el documento PDF real desde la fuente oficial, guarda una copia en `storage/pdfs/elperuano/<año>/` y calcula su SHA-256. Solo se intenta cachear PDF para registros clasificados como `relevant` o `review`. Una ejecución posterior reutiliza el archivo si su hash continúa siendo válido.

También existe un proceso periódico:

```bash
radar-laboral-sync-daemon
```

Por defecto sincroniza cada 6 horas. Puede cambiarse con `RADAR_SYNC_INTERVAL_SECONDS`; el programa impone un mínimo de una hora para no consultar innecesariamente la fuente oficial.

## Carga histórica de El Peruano

El backfill histórico reutiliza exactamente el mismo collector por fecha que la sincronización diaria. Esto evita tener dos parsers distintos para la misma fuente y conserva las mismas reglas de integridad para `NL` y `EX`.

Ejemplo, primero solo metadatos:

```bash
radar-laboral-backfill --from 2026-01-01 --to 2026-01-31 --no-pdf
```

Luego, si se desea completar las copias locales de documentos laborales del mismo rango:

```bash
radar-laboral-backfill --from 2026-01-01 --to 2026-01-31
```

El rango es inclusivo, se procesa día por día y el `upsert` permite repetir una carga sin duplicar registros por OP. Los metadatos de edición (`regular` / `extraordinary`) se conservan en el catálogo JSONL.

La prueba de integración conocida para el **1 de agosto de 2026** es 124 dispositivos `NL` + 16 `EX` = **140 dispositivos**.

## SUNAFIL — Tribunal de Fiscalización Laboral

La biblioteca de jurisprudencia puede alimentarse con las Resoluciones de Sala Plena publicadas por SUNAFIL:

```bash
radar-laboral-sync-tfl --all-pages --no-pdf
```

El modo normal procesa solo la primera página del listado para reducir tráfico. `--all-pages` recorre el histórico disponible y `--refresh-details` vuelve a consultar detalles ya almacenados.

Los registros usan IDs estables derivados del recurso oficial de `gob.pe`, por ejemplo `sunafil-tfl:6556395`. El collector conserva número, fecha, sumilla oficial, fuente, PDF y SHA-256 cuando existe copia local. `binding_level` solo se informa cuando el texto oficial declara expresamente una fuerza o alcance obligatorio; el sistema no lo infiere por el tipo de resolución.

El gate live de creación del collector validó 53 resoluciones disponibles en ese momento y la Resolución de Sala Plena `001-2025-SUNAFIL-TFL`, incluida su sumilla completa, su declaración de precedente administrativo de observancia obligatoria y su PDF oficial. Ver [`docs/QA_TFL.md`](docs/QA_TFL.md).

## Docker

Despliegue recomendado:

```bash
docker compose up -d --build
```

Compose levanta dos procesos basados en la misma imagen:

- `radar-laboral`: interfaz web;
- `radar-laboral-sync`: sincronizador periódico de El Peruano.

Ambos comparten `./storage:/data`. Allí quedan de forma persistente:

```text
storage/
├── radar_laboral.db
├── catalog/
│   ├── norms.jsonl
│   └── case_law.jsonl
└── pdfs/
```

La interfaz se publica únicamente en `127.0.0.1:8080`, no en todas las interfaces de red. Esto es deliberado y funciona bien detrás de un reverse proxy o Cloudflare Tunnel.

Para Cloudflare Tunnel, el origen puede apuntar a:

```text
http://localhost:8080
```

No es necesario abrir el puerto 8080 en el router ni exponerlo directamente a Internet.

## Estado y diagnóstico

- `/healthz`: healthcheck mínimo para Docker.
- `/status`: resumen visual de registros, PDFs y última sincronización.
- `/api/status`: la misma información en JSON.
- [`docs/QA_PENDING.md`](docs/QA_PENDING.md): pruebas que requieren Raspberry, fuente real o Cloudflare.
- [`docs/QA_TFL.md`](docs/QA_TFL.md): QA del collector SUNAFIL TFL.

## Actualizar una instalación existente

El directorio `storage/` no se borra al actualizar el código.

```bash
git switch main
git pull --ff-only
docker compose up -d --build
docker compose ps
```

Las migraciones ligeras de SQLite se ejecutan al iniciar la aplicación. Los PDFs y la base local permanecen en el volumen persistente.

## Estado del proyecto

Proyecto en construcción. La base actual incluye aplicación web, modelo de datos, collectors determinísticos de El Peruano y SUNAFIL TFL, clasificación laboral, cache verificable de PDFs, sincronización automática de El Peruano, backfill histórico, biblioteca de jurisprudencia y relaciones entre documentos. Las siguientes fuentes y funcionalidades se incorporarán por etapas.
