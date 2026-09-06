# Experimentos de clasificación híbrida

Radar Laboral mantiene `rules_v4` como comportamiento productivo por defecto. Los modelos locales y LLM vía API se evalúan fuera de producción hasta demostrar una mejora medible, especialmente sin falsos negativos laborales.

## 1. Crear una muestra humana del corpus

Después de completar el histórico, exporta una muestra estratificada:

```bash
radar-laboral-classifier-sample /data/classifier-labels.csv --per-class 100
```

El CSV incluye la predicción actual, score, motivo, URL oficial y columnas vacías `human_label` y `human_notes`. Las etiquetas humanas válidas son `relevant`, `review` y `not_labor`.

No debe usarse la predicción de `rules_v4` como etiqueta gold. La etiqueta humana debe decidirse revisando título/sumilla y, cuando sea necesario, la fuente oficial o el texto legal.

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
