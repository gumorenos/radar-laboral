# Radar Laboral Perú

Repositorio ligero y autocontenido para **capturar, conservar y consultar normativa laboral peruana**, con trazabilidad hacia la fuente oficial y una evolución prevista hacia jurisprudencia y conceptos laborales.

El objetivo del proyecto no es reemplazar a El Peruano, MTPE, SUNAFIL, el Tribunal Constitucional, el Poder Judicial u otras fuentes oficiales. La idea es mantener un repositorio local consultable con metadatos y copias de los documentos oficiales, de modo que cada instalación pueda investigar sin depender de un chat ni de inteligencia artificial.

## Principios

- **Fuente primero:** cada registro conserva URL oficial, URL del PDF y hash del archivo descargado cuando existe copia local.
- **Determinístico por defecto:** captura, almacenamiento, búsqueda y clasificación básica no requieren IA.
- **Ligero:** una aplicación Python, SQLite y una interfaz web simple.
- **Portable:** el mismo código debe correr en Linux, Docker y, más adelante, como ejecutable portable para Windows.
- **Reproducible:** los catálogos pueden exportarse/versionarse como texto; la base SQLite y los PDF se reconstruyen o descargan localmente.
- **Extensible:** jurisprudencia, conceptos, IA, búsqueda semántica y resúmenes pueden añadirse por capas sin convertirse en la fuente de verdad.

## Capas de contenido

Radar Laboral separa tres tipos de información:

1. **Normas:** leyes, decretos, resoluciones y otras disposiciones oficiales.
2. **Jurisprudencia:** sentencias, casaciones, precedentes y criterios administrativos relevantes, almacenados como un tipo de documento distinto.
3. **Conceptos:** explicaciones generales de materias laborales mantenidas como Markdown versionable y enlazadas a sus fuentes.

Ver [`docs/content-model.md`](docs/content-model.md) para el diseño de estas relaciones.

## MVP

La primera versión se concentra en normas y cubre:

1. Catálogo SQLite con metadatos normalizados.
2. Interfaz web para buscar y filtrar normas.
3. Cache local de los PDF oficiales con SHA-256.
4. Colector determinístico de El Peruano.
5. Clasificación determinística de relevancia laboral.
6. Sincronización periódica, deduplicación y registro de ejecuciones.
7. Backfill histórico determinístico por rango de fechas.
8. Docker para servidor Linux.
9. Preparación para empaquetado portable en Windows.

La jurisprudencia y la biblioteca de conceptos están contempladas en el modelo desde el inicio, pero se incorporarán después de estabilizar la captura de normativa.

## Arquitectura

```text
Fuentes oficiales
      |
      v
  collectors  ---> catálogo JSONL
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

## Carga histórica

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

Para históricos grandes conviene trabajar por meses o trimestres. Si una fecha falla por integridad, los días anteriores ya almacenados permanecen disponibles y el rango puede repetirse después de corregir la causa.

La prueba de integración conocida para el **1 de agosto de 2026** es 124 dispositivos `NL` + 16 `EX` = **140 dispositivos**. Este gate debe validarse en una máquina con acceso real a El Peruano antes de considerar estable el backfill.

## Docker

Despliegue recomendado:

```bash
docker compose up -d --build
```

Compose levanta dos procesos basados en la misma imagen:

- `radar-laboral`: interfaz web;
- `radar-laboral-sync`: sincronizador periódico.

Ambos comparten `./storage:/data`. Allí quedan de forma persistente:

```text
storage/
├── radar_laboral.db
├── catalog/norms.jsonl
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

También puede revisarse desde consola:

```bash
docker compose ps
docker compose logs --tail=100 radar-laboral-sync
```

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

Proyecto en construcción. La base actual incluye aplicación web, modelo de datos, collector determinístico por fecha de El Peruano, clasificación laboral, cache verificable de PDFs, sincronización automática, backfill histórico y estructura futura para jurisprudencia y conceptos laborales. Las siguientes fuentes y funcionalidades se incorporarán por etapas.
