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

El comando consulta la publicación de Normas Legales, normaliza los dispositivos encontrados, clasifica su relevancia laboral, hace `upsert` en SQLite y actualiza el catálogo JSONL.

El inventario conserva todos los dispositivos detectados. Para evitar convertir la instalación en un archivo masivo de documentos no laborales, la copia PDF local se descarga solo para registros clasificados como `Relevante` o `Revisar`. Cada PDF local conserva SHA-256 y se vuelve a obtener desde la fuente oficial si su contenido deja de coincidir con el hash registrado.

Para comprobar solo metadatos sin intentar descargar PDF:

```bash
radar-laboral-sync --no-pdf
```

También existe un proceso periódico:

```bash
radar-laboral-sync-daemon
```

Por defecto sincroniza cada 6 horas. Puede cambiarse con `RADAR_SYNC_INTERVAL_SECONDS`; el programa impone un mínimo de una hora para no consultar innecesariamente la fuente oficial.

## Carga histórica

El buscador oficial de El Peruano permite consultar dispositivos de Normas Legales por fecha. Radar Laboral usa ese mecanismo para reconstruir el histórico día por día y verificar que la cantidad de registros normalizados coincida con el total informado por la fuente.

Ejemplo, primero solo metadatos:

```bash
radar-laboral-backfill --from 2026-01-01 --to 2026-01-31 --no-pdf
```

Luego, si se desea completar las copias locales de los documentos laborales del mismo rango:

```bash
radar-laboral-backfill --from 2026-01-01 --to 2026-01-31
```

El backfill:

- consulta un día por vez;
- pagina los resultados del buscador oficial;
- deduplica por Orden de Publicación (OP);
- conserva también dispositivos oficiales sin número;
- aborta si El Peruano declara más dispositivos de los que el parser logró normalizar;
- hace `upsert`, por lo que repetir un rango no duplica registros;
- descarga PDF únicamente para `Relevante` y `Revisar` salvo que se use `--no-pdf`.

Para históricos grandes conviene ejecutarlo por meses o trimestres. Así es más sencillo revisar falsos positivos, reanudar un rango y controlar el crecimiento de `storage/`.

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

Proyecto en construcción. La base actual incluye aplicación web, modelo de datos, colector de El Peruano, clasificación laboral, cache verificable de PDFs, sincronización automática, backfill histórico y estructura futura para jurisprudencia y conceptos laborales. Las siguientes fuentes y funcionalidades se incorporarán por etapas.
