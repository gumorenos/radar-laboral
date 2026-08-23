# Catálogo versionable

Este directorio contiene la información normalizada que sí conviene versionar en Git.

La idea es separar tres capas de conocimiento:

```text
catalog/
  norms.jsonl              # normas y disposiciones
  case-law.jsonl           # jurisprudencia y criterios relevantes
  concepts/                # explicaciones generales en Markdown
    vacaciones.md
    cts.md
    horas-extras.md
```

## Normas

Cada línea de `norms.jsonl` será un objeto JSON independiente con metadatos de la norma y trazabilidad hacia la fuente oficial.

## Jurisprudencia

`case-law.jsonl` almacenará registros normalizados de sentencias, casaciones, precedentes y criterios administrativos relevantes. Además de la fuente y el PDF, cada registro podrá indicar órgano, expediente o número, materia, fecha de decisión y nivel de obligatoriedad o fuerza del criterio cuando sea determinable.

La jurisprudencia no se tratará como una norma. Tendrá su propio tipo de registro, aunque podrá relacionarse con normas y conceptos.

## Conceptos

Las explicaciones generales vivirán como archivos Markdown en `catalog/concepts/`. Esto permite que sean legibles, fáciles de editar y completamente versionables mediante pull requests.

Cada concepto podrá incluir:

- explicación en lenguaje claro;
- reglas principales;
- ejemplos;
- preguntas frecuentes;
- normas aplicables;
- jurisprudencia relacionada;
- fecha de última revisión.

Los conceptos son contenido explicativo, no una fuente jurídica primaria.

## Relaciones

La base local podrá relacionar registros de los tres tipos. Ejemplos:

- una casación `interprets` una norma;
- una sentencia `applies` una norma;
- un concepto `explains` una norma;
- una sentencia `supports` o `limits` un concepto;
- una norma `amends` o `repeals` otra norma.

Estas relaciones permitirán navegar desde una norma hacia la jurisprudencia relacionada y desde un concepto hacia sus fuentes.

## SQLite y PDF

La base SQLite de cada instalación se reconstruye a partir del catálogo y luego se completa mediante sincronización con las fuentes oficiales.

Los PDF no se almacenan normalmente en Git; se descargan a `storage/pdfs/` y cada registro conserva su URL oficial y SHA-256. Los releases podrán incluir snapshots de datos o PDF cuando resulte conveniente.
