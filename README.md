# Radar Laboral Perú

Repositorio ligero y autocontenido para **capturar, conservar y consultar normativa y jurisprudencia laboral peruana**, con trazabilidad hacia la fuente oficial y una evolución prevista hacia conceptos laborales e IA opcional.

El objetivo del proyecto no es reemplazar a El Peruano, MTPE, SUNAFIL, el Tribunal Constitucional, el Poder Judicial u otras fuentes oficiales. La idea es mantener un repositorio local consultable con metadatos y copias de los documentos oficiales.

## Principios

- **Fuente primero:** cada registro conserva URL oficial, URL del PDF y hash del archivo descargado cuando existe copia local.
- **Determinístico por defecto:** captura, almacenamiento, búsqueda y clasificación básica no requieren IA.
- **Separación jurídica:** normas y jurisprudencia son entidades distintas; el sistema no presume fuerza vinculante donde la fuente no la declara.
- **Ligero:** Python, Flask, Waitress y SQLite.
- **Portable:** Linux/Docker y, más adelante, ejecutable portable para Windows.
- **Reproducible:** catálogos JSONL reconstruibles/versionables; SQLite y PDFs permanecen locales.

## Capas de contenido

1. **Normas:** leyes, decretos, resoluciones y otras disposiciones oficiales.
2. **Jurisprudencia:** sentencias, casaciones, precedentes y criterios administrativos relevantes.
3. **Conceptos:** explicaciones laborales mantenidas como Markdown y enlazadas a fuentes.

Ver [`docs/content-model.md`](docs/content-model.md).

## Funcionalidad actual

- catálogo SQLite de normas y jurisprudencia;
- interfaz web con ficha individual de cada norma y pronunciamiento;
- búsqueda FTS5 opcional para normas, con fallback `LIKE`;
- filtros y paginación;
- relaciones auditables entre documentos (`interprets`, `applies`, `amends`, etc.);
- cache local de PDFs con SHA-256;
- collector determinístico de El Peruano;
- backfill histórico de El Peruano por rango de fechas;
- collector de Resoluciones de Sala Plena del Tribunal de Fiscalización Laboral de SUNAFIL;
- sincronización periódica de El Peruano y registro de ejecuciones.

## Desarrollo local

Requiere Python 3.11 o superior.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
radar-laboral --open-browser
```

La aplicación usa por defecto `./storage/radar_laboral.db` y escucha en `http://127.0.0.1:8080`.

Rutas principales:

- `/`: normas;
- `/jurisprudencia`: jurisprudencia;
- `/status`: estado de sincronización.

## Sincronizar El Peruano

```bash
radar-laboral-sync
```

Consulta el buscador oficial de El Peruano para la fecha local de Lima, separando Normas Legales (`NL`) y Edición Extraordinaria (`EX`). Un estado explícito `No hay resultados para mostrar` se considera éxito con cero registros; HTML ambiguo o totales inconsistentes siguen siendo errores.

Fecha concreta / solo metadatos:

```bash
radar-laboral-sync --date 2026-08-23 --no-pdf
```

Los PDF laborales se guardan en `storage/pdfs/elperuano/<año>/` y se verifican con SHA-256.

## Carga histórica de El Peruano

```bash
radar-laboral-backfill --from 2026-01-01 --to 2026-01-31 --no-pdf
```

El rango es inclusivo y reutiliza el mismo collector por fecha. El gate de integración conocido para el **1 de agosto de 2026** es 124 dispositivos `NL` + 16 `EX` = **140 dispositivos**.

## Jurisprudencia: SUNAFIL TFL

El primer collector jurisprudencial usa la sección oficial **Resolución de Sala Plena** del Tribunal de Fiscalización Laboral de SUNAFIL.

Sincronización normal —solo la primera página de resoluciones recientes:

```bash
radar-laboral-sync-tfl --no-pdf
```

Carga de todo el histórico disponible:

```bash
radar-laboral-sync-tfl --all-pages --no-pdf
```

Después, para cachear PDFs oficiales:

```bash
radar-laboral-sync-tfl --all-pages
```

El collector obtiene el detalle completo solo cuando el registro es nuevo o le falta sumilla/PDF. `--refresh-details` fuerza una relectura de los detalles existentes.

La fuerza jurídica **no se infiere por ser una Resolución de Sala Plena**. `binding_level` solo se informa cuando la sumilla oficial contiene lenguaje explícito como “precedente administrativo de observancia obligatoria” o “criterios de observancia obligatoria”.

Los PDFs se guardan en `storage/pdfs/sunafil-tfl/<año>/` y el catálogo reproducible en `storage/catalog/case_law.jsonl`.

> El collector TFL todavía no forma parte del daemon de 6 horas. Primero se valida como comando manual/CI; la integración periódica se hará después de estabilizar el live gate.

## Sincronización periódica

```bash
radar-laboral-sync-daemon
```

Actualmente sincroniza El Peruano cada 6 horas. Puede configurarse con `RADAR_SYNC_INTERVAL_SECONDS`; se impone un mínimo de una hora.

## Docker

```bash
docker compose up -d --build
```

Compose levanta:

- `radar-laboral`: interfaz web;
- `radar-laboral-sync`: daemon de El Peruano.

Ambos comparten `./storage:/data`:

```text
storage/
├── radar_laboral.db
├── catalog/
│   ├── norms.jsonl
│   └── case_law.jsonl
└── pdfs/
    ├── elperuano/
    └── sunafil-tfl/
```

La interfaz se publica solo en `127.0.0.1:8080`, apropiado para reverse proxy o Cloudflare Tunnel.

## Estado y diagnóstico

- `/healthz`: healthcheck mínimo;
- `/status`: estado visual;
- `/api/status`: estado JSON;
- [`docs/QA_PENDING.md`](docs/QA_PENDING.md): QA que requiere Raspberry/Cloudflare/PDFs reales;
- [`docs/QA_FTS.md`](docs/QA_FTS.md): smoke opcional de FTS5.

## Actualizar una instalación existente

```bash
git switch main
git pull --ff-only
docker compose up -d --build
docker compose ps
```

`storage/` no se elimina al actualizar y las migraciones ligeras de SQLite se ejecutan al iniciar.

## Estado del proyecto

La base actual ya incluye normas, jurisprudencia, búsqueda, filtros, paginación, fichas, relaciones, El Peruano y el primer collector TFL. Próximas capas: estabilizar collectors jurisprudenciales adicionales, conceptos laborales y posteriormente una interfaz de IA opcional sustentada únicamente en el corpus indexado.
