# Arquitectura inicial

## Objetivo

Radar Laboral Perú debe poder ejecutarse como:

1. servicio ligero en un servidor Linux;
2. contenedor Docker reproducible;
3. aplicación local portable en Windows;
4. proyecto abierto que cualquier colega pueda clonar y desplegar.

La arquitectura inicial evita servicios externos obligatorios y separa claramente **código**, **catálogo versionable** y **datos de ejecución**.

## Componentes

### 1. Aplicación

Una sola aplicación Python expone una interfaz web y consulta SQLite. Se usa Flask por su bajo peso y Waitress como servidor WSGI multiplataforma.

No se requiere Node.js ni un frontend separado.

### 2. SQLite local

Cada instalación mantiene una base SQLite en:

```text
storage/radar_laboral.db
```

La base es un artefacto de ejecución, no la fuente canónica del repositorio. Puede regenerarse a partir del catálogo versionable y volver a sincronizarse con las fuentes oficiales.

### 3. Catálogo versionable

La información normalizada que sí conviene conservar en Git debe vivir en archivos de texto, inicialmente JSONL, por ejemplo:

```text
catalog/norms.jsonl
```

Ventajas frente a versionar directamente el `.db`:

- diffs legibles;
- merge y revisión mediante pull requests;
- historial por registro;
- menor riesgo de conflictos/binarios corruptos;
- posibilidad de reconstruir SQLite en cualquier plataforma.

### 4. PDFs

Los PDF oficiales se descargan localmente a:

```text
storage/pdfs/<source>/<year>/<id>.pdf
```

No se incorporan al historial normal de Git porque el crecimiento acumulativo sería rápido y los binarios no generan diffs útiles.

Cada registro conserva:

- URL oficial;
- URL del PDF;
- ruta local opcional;
- SHA-256 del PDF descargado;
- fecha de captura.

Así es posible verificar que la copia local corresponde al documento capturado.

Más adelante se puede generar un release o snapshot con un conjunto de PDF si resulta útil, sin obligar a que cada clon del repositorio arrastre todo el archivo histórico.

## Modelo mínimo de norma

| Campo | Propósito |
| --- | --- |
| `id` | Identificador estable y reproducible |
| `source` | Fuente: El Peruano, MTPE, SUNAFIL, etc. |
| `document_type` | Ley, Decreto Supremo, Resolución, etc. |
| `number` | Número oficial de la norma |
| `title` | Sumilla o título oficial |
| `summary` | Resumen opcional; no es fuente de verdad |
| `publication_date` | Fecha de publicación |
| `effective_date` | Fecha de vigencia cuando sea determinable |
| `issuer` | Entidad emisora |
| `topic` | Clasificación temática básica |
| `status` | Vigente, futura, derogada, proyecto, etc. |
| `official_url` | Página oficial |
| `pdf_url` | URL oficial del PDF |
| `pdf_path` | Copia local opcional |
| `sha256` | Huella del PDF local |
| `captured_at` | Momento en que se capturó el registro |
| `updated_at` | Última actualización conocida |

## Sincronización

El flujo previsto es:

```text
collector -> normalizer -> catalog JSONL -> SQLite -> web
                      \-> PDF cache
```

Cada colector debe ser idempotente: ejecutar la sincronización dos veces no debe crear duplicados.

## Despliegue en servidor

La opción recomendada para el servidor personal es Docker Compose con un único contenedor y un volumen persistente `./storage`.

Para una exposición pública se puede colocar Caddy, nginx o el proxy ya existente del servidor delante de Radar Laboral. HTTPS y autenticación quedan fuera del proceso Python.

## Windows

La aplicación está pensada para empaquetarse con PyInstaller como un ejecutable que:

1. crea `storage/` junto al ejecutable o en una ubicación configurable;
2. levanta el servidor local en `127.0.0.1`;
3. abre el navegador predeterminado;
4. usa la misma SQLite y los mismos colectores que Linux.

El release de Windows puede distribuirse como:

```text
radar-laboral-windows-x64.zip
  radar-laboral.exe
  README.txt
  storage/
```

No hace falta construir una interfaz de escritorio nativa; el navegador funciona como interfaz y mantiene una sola base de código.

## Releases

GitHub Actions podrá crear posteriormente:

- imagen Docker o artefacto para Linux;
- ZIP portable de Windows x64;
- checksums SHA-256;
- opcionalmente un snapshot inicial del catálogo.

La aplicación debe funcionar aun sin IA. Cualquier capa de IA futura se tratará como un servicio opcional para búsqueda semántica, clasificación o resumen, nunca como fuente primaria de la norma.
