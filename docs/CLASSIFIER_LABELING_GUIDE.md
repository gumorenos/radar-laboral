# Guía de etiquetado humano del clasificador

Esta guía define las etiquetas gold del benchmark de Radar Laboral. La decisión debe basarse en la evidencia oficial visible y no en la predicción de `rules_v4`, scores u otros modelos.

## Etiquetas

### `relevant`

Use `relevant` cuando la norma tenga contenido sustantivo directamente relacionado con relaciones laborales o gestión de obligaciones laborales.

Incluye, entre otros:

- remuneraciones, beneficios, CTS, gratificaciones y vacaciones;
- jornada, descansos, horas extra y feriados;
- contratación, modalidades contractuales y desvinculación;
- seguridad y salud en el trabajo;
- inspección del trabajo y sanciones laborales;
- relaciones colectivas, negociación colectiva, huelga y sindicatos;
- tercerización e intermediación laboral;
- teletrabajo;
- hostigamiento/acoso e igualdad en el empleo;
- licencias y derechos familiares;
- trabajadores extranjeros;
- planillas, registros laborales y tratamiento de datos del trabajador cuando la obligación sea laboral.

La norma no necesita imponer una obligación nueva: también puede modificar, reglamentar, interpretar, prorrogar o derogar una regla laboral.

### `not_labor`

Use `not_labor` cuando la norma no tenga contenido laboral sustantivo.

Ejemplos frecuentes:

- designaciones, renuncias y encargaturas de funcionarios;
- autorizaciones de viaje o comisiones de servicio;
- delegaciones administrativas de facultades;
- asuntos presupuestales, tributarios, sectoriales o regulatorios sin efecto laboral sustantivo;
- actos internos de organización;
- normas cuyo único vínculo con personas sea administrativo y no regule relaciones de trabajo.

Que una entidad sea MTPE o SUNAFIL no convierte por sí solo una norma en laboral.

### `review`

Use `review` solo cuando la evidencia disponible no permita decidir responsablemente entre `relevant` y `not_labor`, o cuando exista una relación laboral plausible pero indirecta/ambigua que requiera leer más fuente oficial.

`review` no significa "importancia media" ni "no estoy seguro por rapidez". Debe representar incertidumbre real del contenido disponible.

Casos típicos:

- título demasiado genérico y evidencia insuficiente;
- texto truncado antes de las disposiciones relevantes;
- norma transversal donde no queda claro si las disposiciones alcanzan relaciones laborales;
- referencia a otra norma laboral sin suficiente contexto para saber qué modifica.

## Reglas de consistencia

1. Etiquete el documento, no la institución que lo emite.
2. Priorice el contenido normativo sobre palabras clave aisladas.
3. Una designación administrativa sigue siendo `not_labor` aunque mencione "trabajo", "personal" o una entidad laboral.
4. Si existe evidencia oficial suficiente, evite `review`: decida `relevant` o `not_labor`.
5. Si la evidencia es solo `title_only` y el título no permite una decisión fiable, use `review`.
6. Use `human_notes` para casos frontera, evidencia insuficiente o decisiones que convenga auditar después.
7. No consulte las predicciones actuales del clasificador durante el etiquetado gold.

## Objetivo del benchmark

El benchmark prioriza evitar falsos negativos laborales. Sin embargo, el anotador no debe sesgar cada decisión hacia `relevant` por esa prioridad: la etiqueta debe reflejar el contenido real. El gate de evaluación será quien penalice especialmente los falsos negativos.
