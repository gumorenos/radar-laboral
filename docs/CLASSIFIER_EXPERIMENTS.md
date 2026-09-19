# Experimentos de clasificación híbrida

Radar Laboral mantiene `rules_v4` como comportamiento productivo por defecto. Los modelos locales y LLM vía API se evalúan fuera de producción hasta demostrar una mejora medible, especialmente sin falsos negativos laborales.

## 1. Crear una muestra humana del corpus

Después de completar el histórico, exporta una muestra estratificada ciega:

```bash
radar-laboral-classifier-sample /data/classifier-labels.csv --per-class 100
```

Por defecto el CSV **no** incluye predicción, score, motivo ni método actuales. Solo `--include-model-output` los añade de forma explícita; esa opción no debe utilizarse para construir el benchmark gold porque puede introducir sesgo de anclaje. Las etiquetas humanas válidas son `relevant`, `review` y `not_labor`.

### Muestra ciega enriquecida

Si título y metadatos no bastan para etiquetar, genera evidencia oficial adicional sin revelar la salida de `rules_v4`:

```bash
radar-laboral-classifier-sample \
  /data/classifier-labels-blind-enriched.csv \
  --per-class 100 \
  --enrich
```

La prioridad de evidencia es:

1. `summary` almacenado, cuando existe;
2. texto extraído del PDF oficial ya cacheado;
3. texto extraído temporalmente del PDF oficial remoto, sin persistirlo;
4. texto recuperable desde la página oficial, anclado en el título del documento cuando es posible;
5. título como fallback.

El CSV enriquecido añade `evidence_source`, `evidence_chars` y `evidence_text`. `evidence_source` puede ser `summary`, `cached_pdf`, `remote_pdf`, `official_page` o `title_only`. En modo ciego no muestra `classification_text_excerpt`, predicción, score, reason ni método del clasificador. El PDF remoto usado para enriquecer la muestra se procesa en memoria y no se incorpora al cache productivo.

Para enriquecer **exactamente los mismos IDs** de una muestra previa, sin volver a sortear el corpus:

```bash
radar-laboral-classifier-sample \
  /data/classifier-labels-blind-enriched.csv \
  --from-csv /data/classifier-labels-blind.csv \
  --enrich
```

`--no-official-fetch` limita el enriquecimiento a información local. `--evidence-max-chars` controla el máximo por fila y `--official-delay` permite espaciar consultas a la fuente oficial.

No debe usarse la predicción de `rules_v4` como etiqueta gold. La etiqueta humana debe decidirse revisando la evidencia oficial disponible. Al convertir un CSV enriquecido, `radar-laboral-classifier-gold` pasa `evidence_text` al campo de texto legal que utiliza el benchmark, pero solo después de que exista la etiqueta humana.

Ejemplo de conversión:

```bash
radar-laboral-classifier-gold \
  /data/classifier-labels-blind-enriched.csv \
  benchmarks/classifier_corpus_gold_v1.jsonl
```

## 2. Comparar modelos locales

Instala las dependencias opcionales en una máquina de evaluación, no en la Raspberry de producción:

```bash
pip install -e '.[semantic]'
```

Ejecuta el benchmark versionado con los modelos predeterminados:

```bash
radar-laboral-classifier-experiment benchmarks/classifier_official_v2.jsonl --default-local-models
```

Actualmente se proponen como candidatos iniciales:

- `intfloat/multilingual-e5-small`
- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`

También puede repetirse `--local-model MODEL` para probar otros modelos. Los modelos se cargan secuencialmente para evitar mantener varios encoders en RAM al mismo tiempo.

## 3. Evaluar un LLM vía API

El adaptador inicial usa el endpoint OpenAI-compatible `/chat/completions` y salida JSON Schema. No se activa en producción y la API key no se persiste.

Variables:

```text
RADAR_LLM_API_KEY=<secreto>
RADAR_LLM_MODEL=<modelo>
RADAR_LLM_BASE_URL=https://api.openai.com/v1
```

Ejemplo:

```bash
radar-laboral-classifier-experiment benchmarks/classifier_official_v2.jsonl --llm
```

Puede usarse un proveedor que implemente el contrato OpenAI-compatible cambiando `RADAR_LLM_BASE_URL` y `RADAR_LLM_MODEL`. Proveedores con API no compatible requieren un adaptador separado; no deben forzarse a este contrato.

El LLM recibe solamente el texto necesario para clasificación, con un máximo de 12 000 caracteres. Devuelve `labor_relevance`, `confidence`, `reason` y evidencia breve. Esa decisión se convierte en una señal semántica para el clasificador híbrido existente; no reemplaza las exclusiones administrativas fuertes.

## 4. Gate de decisión

Orden de prioridad del gate:

1. Cero falsos negativos laborales en el benchmark gold.
2. Mayor `labor_recall`.
3. Mayor `tracked_precision`.
4. Mayor exactitud de 3 clases.

No se habilita un modelo en Raspberry solo porque mejore accuracy. Debe justificar también RAM, latencia, tamaño y complejidad operativa.

## 5. Arquitectura objetivo si el experimento gana

```text
rules_v4
   |
   +-- decisión fuerte -> resultado
   |
   +-- zona incierta -> encoder local ligero
                          |
                          +-- decisión suficiente -> resultado
                          |
                          +-- sigue incierto -> LLM API opcional
                                                |
                                                -> relevant/review/not_labor
```

La clasificación asistida debe conservar versión, modelo/proveedor y evidencia. La fuente oficial y el corpus local siguen siendo la autoridad; el modelo no determina vigencia ni efecto jurídico.
