# Radar Laboral Perú

Repositorio ligero y autocontenido para **capturar, conservar y consultar normativa laboral peruana** con trazabilidad hacia la fuente oficial.

El objetivo del proyecto no es reemplazar a El Peruano, MTPE, SUNAFIL u otras fuentes oficiales. La idea es mantener un catálogo local consultable con metadatos y una copia de los PDF descargados, de modo que cada instalación pueda buscar normas sin depender de un chat ni de inteligencia artificial.

## Principios

- **Fuente primero:** cada registro conserva URL oficial, URL del PDF y hash del archivo descargado.
- **Determinístico por defecto:** captura, almacenamiento, búsqueda y clasificación básica no requieren IA.
- **Ligero:** una aplicación Python, SQLite y una interfaz web simple.
- **Portable:** el mismo código debe correr en Linux, Docker y, más adelante, como ejecutable portable para Windows.
- **Reproducible:** el catálogo versionable vive en Git; la base SQLite y los PDF se reconstruyen/descargan localmente.
- **Extensible:** IA, búsqueda semántica y resúmenes automáticos pueden añadirse después sin convertirse en la fuente de verdad.

## MVP

La primera versión cubrirá:

1. Catálogo SQLite con metadatos normalizados.
2. Interfaz web para buscar y filtrar normas.
3. Cache local de los PDF oficiales.
4. Colector determinístico de una primera fuente oficial.
5. Sincronización incremental y deduplicación.
6. Docker para servidor Linux.
7. Preparación para empaquetado portable en Windows.

## Arquitectura

```text
Fuentes oficiales
      |
      v
  collectors  --->  catálogo versionable (JSONL)
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

## Docker

```bash
docker compose up --build
```

El volumen `./storage` queda fuera de Git y conserva la base local y los PDF descargados.

## Estado

Proyecto en construcción. El esqueleto inicial implementa la aplicación y el modelo de datos; los colectores se incorporarán fuente por fuente después de validar los endpoints y formatos oficiales.
