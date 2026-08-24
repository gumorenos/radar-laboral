# Radar Laboral Perú

Repositorio ligero y autocontenido para **capturar, conservar y consultar normativa laboral peruana y jurisprudencia laboral**, con trazabilidad hacia la fuente oficial.

El objetivo del proyecto no es reemplazar a El Peruano, MTPE, SUNAFIL, el Tribunal Constitucional, el Poder Judicial u otras fuentes oficiales. La idea es mantener un repositorio local consultable con metadatos y copias de los documentos oficiales, de modo que cada instalación pueda investigar sin depender de un chat ni de inteligencia artificial.

## Principios

- **Fuente primero:** cada registro conserva URL oficial, URL del PDF y hash del archivo descargado cuando existe copia local.
- **Determinístico por defecto:** captura, almacenamiento, búsqueda y clasificación básica no requieren IA.
- **Ligero:** Python, SQLite y una interfaz web simple.
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
3. Vista principal que muestra por defecto **laborales relevantes + documentos por revisar**, evitando ocultar señales laborales útiles.
4. Cobertura temporal visible: primera y última fecha presentes en la base.
5. Selector web para solicitar carga histórica de El Peruano desde una fecha, con cola persistente y worker separado.
6. Biblioteca independiente de jurisprudencia con búsqueda, filtros, paginación y fichas.
7. Cache local de PDF oficiales con SHA-256.
8. Collector determinístico de El Peruano por fecha, incluyendo edición regular y extraordinaria.
9. Clasificación determinística de relevancia laboral, versionada y migrable.
10. Sincronización periódica, deduplicación y registro de ejecuciones.
11. Backfill histórico de El Peruano por rango de fechas.
12. Collector de Resoluciones de Sala Plena del Tribunal de Fiscalización Laboral de SUNAFIL.
13. Relaciones auditables entre normas y jurisprudencia.
14. Docker para servidor Linux.
15. Preparación para empaquetado portable en Windows.

## Arquitectura

```text
Fuentes oficiales
      |
      v
 collectors  -----> catálogos JSONL
      |                   |
      v                   v
 storage/pdfs/         SQLite local
      |                   |
      +---------> aplicación web
                       |
                       v
                 cola sync_requests
                       |
                       v
                 worker histórico
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

La sincronización diaria no sustituye un histórico: una instalación nueva puede contener solo días recientes y, si esos días tienen principalmente nombramientos u otros actos internos, la vista laboral puede quedar vacía. La pantalla `/status` muestra por eso la primera y última fecha cargadas y permite solicitar un rango histórico.

El formulario web tiene dos fechas: **Traer desde** y **Hasta**. La solicitud no ejecuta el scraping dentro del request HTTP: se guarda en `sync_requests` y `radar-laboral-worker` la procesa en segundo plano. Si el worker reinicia, un trabajo interrumpido vuelve a la cola; repetir rangos no duplica documentos porque el collector usa `upsert`.

Como el sitio puede estar detrás de un Cloudflare Tunnel público, el POST de carga histórica está deshabilitado salvo que exista una clave administrativa fuerte:

```text
RADAR_ADMIN_TOKEN=<secreto-largo-y-aleatorio>
```

Docker Compose lee ese valor del entorno del host o de un archivo `.env` local que **no debe versionarse**. El selector sigue visible cuando la clave no está configurada, pero aparece deshabilitado. El rango máximo por solicitud es 366 días por defecto y puede cambiarse con `RADAR_MAX_BACKFILL_DAYS`.

Para una primera carga histórica se recomienda **solo metadatos**; luego pueden completarse PDFs laborales en un rango menor. La CLI tradicional sigue disponible:

```bash
radar-laboral-backfill --from 2026-01-01 --to 2026-01-31 --no-pdf
```

El rango es inclusivo, se procesa día por día y conserva edición `regular` / `extraordinary`. La prueba de integración conocida para el **1 de agosto de 2026** es 124 dispositivos `NL` + 16 `EX` = **140 dispositivos**.

## Clasificación laboral

La clasificación es conservadora y versionada. La portada usa `tracked`, que incluye tanto `relevant` como `review`; los actos identificados como administrativos siguen ocultos en esa vista, pero permanecen en el inventario SQLite.

La versión 3 amplía señales específicas de inspección laboral (`función inspectiva`, Sistema/Ley General de Inspección del Trabajo) y, a la vez, reconoce más patrones de nombramientos, conclusiones de designación y encargaturas. Al iniciar una versión nueva, SQLite reclasifica automáticamente filas generadas con una versión anterior del clasificador.

## SUNAFIL — Tribunal de Fiscalización Laboral

La biblioteca de jurisprudencia puede alimentarse con las Resoluciones de Sala Plena publicadas por SUNAFIL:

```bash
radar-laboral-sync-tfl --all-pages --no-pdf
```

El modo normal procesa solo la primera página del listado para reducir tráfico. `--all-pages` recorre el histórico disponible y `--refresh-details` vuelve a consultar detalles ya almacenados.

Los registros usan IDs estables derivados del recurso oficial de `gob.pe`. El collector conserva número, fecha, sumilla oficial, fuente, PDF y SHA-256 cuando existe copia local. `binding_level` solo se informa cuando el texto oficial declara expresamente una fuerza o alcance obligatorio; el sistema no lo infiere por el tipo de resolución.

Ver [`docs/QA_TFL.md`](docs/QA_TFL.md) para el gate real ya ejecutado.

## Docker

Despliegue recomendado:

```bash
docker compose up -d --build
```

Compose usa tres procesos basados en la misma imagen:

- `radar-laboral`: interfaz web;
- `radar-laboral-sync`: sincronizador periódico de El Peruano;
- `radar-laboral-worker`: procesa la cola persistente de cargas históricas.

Los tres comparten `./storage:/data`. Allí quedan de forma persistente:

```text
storage/
├── radar_laboral.db
├── catalog/
│   ├── norms.jsonl
│   └── case_law.jsonl
└── pdfs/
```

La interfaz se publica únicamente en `127.0.0.1:8080`, deliberadamente pensada para un reverse proxy o Cloudflare Tunnel.

## Estado y diagnóstico

- `/healthz`: healthcheck mínimo para Docker.
- `/status`: registros, cobertura temporal, carga histórica, cola y última sincronización.
- `/api/status`: estado equivalente en JSON, sin secretos.
- [`docs/QA_PENDING.md`](docs/QA_PENDING.md): pruebas que requieren Raspberry, fuente real o Cloudflare.
- [`docs/QA_TFL.md`](docs/QA_TFL.md): QA del collector SUNAFIL TFL.

## Actualizar una instalación existente

El directorio `storage/` no se borra al actualizar el código. Las migraciones ligeras de SQLite se ejecutan al iniciar la aplicación, incluidos nuevos objetos como `sync_requests` y reclasificaciones por versión.

```bash
git switch main
git pull --ff-only
docker compose up -d --build
docker compose ps
```

## Estado del proyecto

Proyecto en construcción. La base actual incluye aplicación web, modelo de datos, collectors determinísticos de El Peruano y SUNAFIL TFL, clasificación laboral versionada, cache verificable de PDFs, sincronización automática, carga histórica encolada, biblioteca de jurisprudencia y relaciones entre documentos. Las siguientes fuentes y funcionalidades se incorporarán por etapas.
