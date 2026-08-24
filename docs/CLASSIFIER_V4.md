# Clasificador laboral v4 — enfoque híbrido y conservador

## Objetivo

Reducir falsos negativos sin convertir un modelo semántico en autoridad jurídica. Radar conserva siempre el inventario capturado y usa tres estados operativos:

- `relevant`: evidencia suficiente de materia laboral;
- `review`: existe señal laboral o incertidumbre suficiente para no excluir;
- `not_labor`: evidencia suficiente para ocultar de la vista laboral por defecto.

La portada considera `relevant + review` como documentos **tracked**. Por diseño, un documento `review` no es un falso negativo: sigue visible para control humano.

## Pipeline

```text
metadatos / extracto legal
        |
        v
reglas y referencias jurídicas ----> score de reglas + evidencias
        |
        +---- decisión fuerte? ------> relevant / not_labor
        |
        v
zona incierta
        |
        +---- scorer semántico opcional
        |          |
        |          v
        |      señal 0..1
        |          |
        +----------+
             |
             v
       agregador conservador
             |
             v
     relevant / review / not_labor
```

## Qué significa el score

`classification_score`, `rule_score` y `semantic_score` son **scores de evidencia**, no probabilidades legales calibradas. Un valor `0.92` no significa “92% de probabilidad de que la norma sea laboral”. Sirven para auditar y comparar decisiones entre versiones del clasificador.

## Reglas de seguridad

1. Un acto administrativo fuerte de personal/gestión (`designan`, `aceptan renuncia`, `autorizan viaje`, etc.) no puede ser convertido en laboral por el modelo semántico.
2. Una materia laboral específica o una referencia normativa laboral explícita puede producir una decisión determinística fuerte sin ejecutar el modelo.
3. El modelo semántico solo participa en la zona incierta.
4. Si el modelo no está instalado o falla, Radar vuelve a las reglas y prefiere `review` frente a una exclusión dudosa.
5. El backend semántico no forma parte de la imagen Docker base hasta demostrar mejora objetiva en benchmark y rendimiento aceptable.

## Backend candidato

Se incluye opcionalmente `intfloat/multilingual-e5-small` mediante `radar-laboral[semantic]`. El modelo y los embeddings de anchors positivos/negativos se cargan una sola vez por instancia del scorer.

El backend calcula similitud contra descripciones laborales y no laborales y transforma el **margen** positivo-negativo a un score 0..1. Esa transformación se deberá calibrar con el corpus peruano; no se considera probabilidad.

## Benchmark

`benchmarks/classifier_seed_v1.jsonl` es un corpus semilla versionado. Mezcla controles oficiales conocidos y fixtures de regresión explícitamente marcados. Todavía no pretende ser estadísticamente representativo.

Ejecutar solo reglas:

```bash
radar-laboral-benchmark-classifier benchmarks/classifier_seed_v1.jsonl --fail-on-false-negative
```

Ejecutar con backend semántico opcional:

```bash
pip install -e '.[semantic]'
radar-laboral-benchmark-classifier benchmarks/classifier_seed_v1.jsonl --semantic
```

Métricas principales:

- `labor_recall`: una norma laboral cuenta como recuperada si termina `relevant` **o** `review`;
- `strict_relevant_recall`: proporción de laborales que terminan directamente `relevant`;
- `nonlabor_specificity`: proporción de no laborales correctamente excluidas;
- `tracked_precision`: proporción de documentos visibles (`relevant + review`) que son laborales en el benchmark;
- `false_negatives`: caso laboral que terminó `not_labor`; es la regresión prioritaria.

## Siguiente fase

1. Persistir scores, método, modelo y evidencia JSON por norma.
2. Extraer texto legal selectivo de PDF para documentos ambiguos.
3. Ampliar el benchmark con cientos de documentos reales etiquetados manualmente.
4. Comparar reglas, E5/BGE, NLI y eventualmente embeddings + regresión logística.
5. Habilitar un backend en producción solo si mejora recall/precision sin degradar Raspberry Pi.
