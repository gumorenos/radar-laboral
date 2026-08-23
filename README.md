# Radar Laboral Perú

Repositorio ligero y autocontenido para **capturar, conservar y consultar normativa laboral peruana**, con trazabilidad hacia la fuente oficial y una evolución prevista hacia jurisprudencia y conceptos laborales.

El objetivo del proyecto no es reemplazar a El Peruano, MTPE, SUNAFIL, el Tribunal Constitucional, el Poder Judicial u otras fuentes oficiales. La idea es mantener un repositorio local consultable con metadatos y copias de los documentos oficiales, de modo que cada instalación pueda investigar sin depender de un chat ni de inteligencia artificial.

## Principios

- **Fuente primero:** cada registro conserva URL oficial, URL del PDF y hash del archivo descargado cuando existe copia local.
- **Determinístico por defecto:** captura, almacenamiento, búsqueda y clasificación básica no requieren IA.
- **Ligero:** una aplicación Python, SQLite y una interfaz web simple.
- **Portable:** el mismo código debe correr en Linux, Docker y, más adelante, como ejecutable portable para Windows.
- **Reproducible:** el catálogo versionable vive en Git; la base SQLite y los PDF se reconstruyen/descargan localmente.
- **Extensible:** jurisprudencia, conceptos, IA, búsqueda semántica y resúmenes pueden añadirse por capas sin convertirse en la fuente de verdad.

## Capas de contenido

Radar Laboral separa tres tipos de información:

1. **Normas:** leyes, decretos, resoluciones y otras disposiciones oficiales.
2. **Jurisprudencia:** sentencias, casaciones, precedentes y criterios administrativos relevantes, almacenados como un tipo de documento distinto.
3. **Conceptos:** explicaciones generales de materias laborales mantenidas como Markdown versionable y enlazadas a sus fuentes.

Ver [`docs/content-model.md`](docs/content-model.md) para el diseño de estas relaciones.

## MVP

La primera versión se concentra en normas y cubrirá:

1. Catálogo SQLite con metadatos normalizados.
2. Interfaz web para buscar y filtrar normas.
3. Cache local de los PDF oficiales.
4. Colector determinístico de El Peruano.
5. Sincronización incremental y deduplicación.
6. Docker para servidor Linux.
7. Preparación para empaquetado portable en Windows.

La jurisprudencia y la biblioteca de conceptos están contempladas en el modelo desde el inicio, pero se incorporarán después de estabilizar la captura de normativa.

## Arquitectura

```text
Fuentes oficiales
      |
      v
  collectors  --->  catálogo versionable (JSONL / Markdown)
      |                    |
      v                    v
 storage/pdfs/          SQLite local
      |                    |
      +---------> aplicación web
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

```bash
radar-laboral-sync
```

El comando consulta la publicación diaria de Normas Legales, normaliza los dispositivos encontrados, hace `upsert` en SQLite y actualiza `catalog/norms.jsonl`.

Cuando puede resolver el documento PDF real desde el visor oficial, guarda una copia en `storage/pdfs/elperuano/<año>/` y calcula su SHA-256. Si el PDF no puede resolverse, conserva el enlace oficial sin interrumpir la sincronización.

Para comprobar solo metadatos sin intentar descargar PDF:

```bash
radar-laboral-sync --no-pdf
```

## Docker

```bash
docker compose up --build
```

El volumen `./storage` queda fuera de Git y conserva la base local y los PDF descargados.

## Estado

Proyecto en construcción. El esqueleto inicial incluye la aplicación web, el modelo de datos, el primer colector de El Peruano y la estructura futura para jurisprudencia y conceptos laborales. Las siguientes fuentes y funcionalidades se incorporarán por etapas.
