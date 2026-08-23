# Modelo de conocimiento

Radar Laboral Perú separa tres tipos de contenido para no mezclar fuentes jurídicas con material explicativo.

## 1. Normas

Representan disposiciones oficiales publicadas por fuentes como El Peruano, MTPE, SUNAFIL u otras entidades.

Campos principales:

- identificador estable;
- fuente;
- tipo y número;
- entidad emisora;
- fecha de publicación y, cuando sea determinable, fecha de vigencia;
- sumilla o título oficial;
- estado;
- tema;
- URL oficial;
- URL y copia local del PDF;
- SHA-256 de la copia local.

La norma y su PDF oficial son fuente primaria. Los resúmenes o clasificaciones son metadatos auxiliares.

## 2. Jurisprudencia

La jurisprudencia se almacena separadamente porque no equivale a una norma.

Fuentes previstas incluyen, según relevancia laboral:

- Tribunal Constitucional;
- Corte Suprema y salas laborales;
- precedentes y resoluciones de órganos administrativos relevantes;
- Tribunal de Fiscalización Laboral de SUNAFIL;
- otros criterios oficiales que resulten útiles para interpretar obligaciones laborales.

Campos principales:

- órgano o tribunal;
- tipo de pronunciamiento;
- número o expediente;
- fecha de decisión y publicación;
- materia;
- criterio o sumilla;
- nivel de obligatoriedad o fuerza del criterio, cuando sea determinable;
- URL y PDF oficial;
- SHA-256 de la copia local.

El sistema debe distinguir claramente entre un criterio vinculante, un precedente, una casación, una sentencia individual y un criterio administrativo no vinculante.

## 3. Conceptos laborales

Los conceptos son material explicativo mantenido dentro del repositorio como Markdown versionable.

Ejemplos:

- vacaciones;
- CTS;
- gratificaciones;
- horas extras;
- período de prueba;
- despido arbitrario;
- teletrabajo;
- tercerización;
- hostigamiento sexual;
- seguridad y salud en el trabajo.

Cada concepto puede incluir:

1. explicación en lenguaje claro;
2. definición técnica;
3. reglas principales;
4. ejemplos;
5. preguntas frecuentes;
6. normas aplicables;
7. jurisprudencia relacionada;
8. fecha de última revisión.

Los conceptos nunca reemplazan a las fuentes primarias. La interfaz debe mostrar de manera visible la fecha de revisión y los enlaces hacia las normas o pronunciamientos que sustentan la explicación.

## Relaciones

La tabla `document_relations` permite conectar elementos entre sí sin convertirlos en una sola entidad.

Tipos de relación previstos:

- `amends`: una norma modifica otra;
- `repeals`: una norma deroga otra;
- `regulates`: una norma reglamenta otra;
- `interprets`: una decisión interpreta una norma;
- `applies`: una decisión aplica una norma;
- `explains`: un concepto explica una norma o criterio;
- `supports`: una fuente sustenta una explicación;
- `limits`: una decisión o norma limita el alcance de otra interpretación.

La taxonomía podrá ampliarse, pero los valores deben permanecer explícitos y auditables.

## Evolución de la interfaz

La interfaz podrá crecer por etapas:

1. **Normas**: buscador, filtros y PDF.
2. **Jurisprudencia**: buscador y navegación por órgano, expediente y materia.
3. **Conceptos**: biblioteca explicativa enlazada a fuentes.
4. **Relaciones**: paneles de “normas relacionadas”, “jurisprudencia relacionada” y “conceptos relacionados”.
5. **Preguntar**: capa opcional de IA que responda únicamente sobre el corpus indexado y cite las fuentes utilizadas.

La cuarta y quinta etapas no son requisito para que las tres primeras funcionen de forma determinística.
