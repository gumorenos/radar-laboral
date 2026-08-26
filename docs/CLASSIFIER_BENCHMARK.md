# Benchmark del clasificador laboral

## Objetivo

El benchmark protege el objetivo principal de Radar Laboral: **no perder normas laborales** y, al mismo tiempo, reducir falsos positivos administrativos. El sistema usa tres estados:

- `relevant`: materia laboral suficientemente clara para mostrarse como norma laboral.
- `review`: posible relevancia laboral, política sectorial o caso fronterizo que debe permanecer visible para revisión.
- `not_labor`: evidencia suficiente de que el documento no es una novedad normativa laboral para el radar.

Para seguridad, `relevant` y `review` cuentan como documentos **tracked**. Un caso laboral esperado que termine como `not_labor` es un falso negativo.

## Corpus

- `classifier_seed_v1.jsonl`: fixtures de regresión y controles iniciales.
- `classifier_official_v2.jsonl`: casos etiquetados a partir de publicaciones oficiales de El Peruano, con `source_url` y una nota de fundamento de la etiqueta.

El corpus oficial incluye negativos difíciles de autoridades laborales (designaciones, renuncias y actos internos) y casos donde palabras como `teletrabajo`, `seguridad y salud en el trabajo`, `promoción del empleo` o `SUNAFIL` aparecen sin que exista un cambio normativo laboral sustantivo.

El corpus aún **no es estadísticamente representativo** del universo de El Peruano. Sus métricas deben interpretarse como pruebas de regresión, no como una estimación de precisión poblacional.

## Métricas

`radar-laboral-benchmark-classifier` reporta:

- `labor_recall`: proporción de casos laborales (`relevant` o `review`) que permanecen visibles.
- `strict_relevant_recall`: proporción de casos esperados como `relevant` que se clasifican exactamente `relevant`.
- `review_exact_recall`: proporción de casos esperados como `review` que permanecen exactamente en revisión.
- `nonlabor_specificity`: proporción de negativos que se excluyen correctamente.
- `tracked_precision`: proporción de elementos mostrados como `relevant/review` que realmente pertenecen al conjunto laboral/revisión del benchmark.
- `exact_accuracy`: coincidencia exacta entre los tres estados.
- matriz `confusion` y listas de mismatches.

El gate crítico de CI sigue siendo **cero falsos negativos conocidos**.

## Experimento E5 (24 de agosto de 2026)

Se ejecutó temporalmente `intfloat/multilingual-e5-small` mediante `sentence-transformers` en GitHub Actions sobre el benchmark semilla de 20 casos.

Resultados sobre ese corpus:

| Métrica | Rules v4 | Rules v4 + E5 |
| --- | ---: | ---: |
| labor recall | 1.0000 | 1.0000 |
| strict relevant recall | 1.0000 | 1.0000 |
| nonlabor specificity | 1.0000 | 1.0000 |
| tracked precision | 1.0000 | 1.0000 |

E5 no cambió ninguna decisión. Solo fue consultado en tres negativos inciertos y los mantuvo como `not_labor`.

Coste observado en runner x86 de GitHub Actions:

- carga del modelo: ~14.8 s;
- evaluación de 20 casos después de cargar: ~0.08 s;
- máximo RSS del proceso: ~1.54 GB;
- cache Hugging Face: ~471 MB;
- el extra `sentence-transformers` instaló PyTorch y numerosas dependencias CUDA en Linux.

### Decisión

**No habilitar `sentence-transformers`/PyTorch en la Raspberry Pi.** El backend queda únicamente como referencia experimental. Si un corpus oficial mayor demuestra beneficio semántico material, evaluar primero una ruta CPU liviana, preferentemente ONNX Runtime/OpenVINO o un clasificador sobre embeddings precalculados.

El score semántico nunca sustituye las exclusiones determinísticas fuertes ni se interpreta como probabilidad jurídica calibrada.
