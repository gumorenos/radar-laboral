# Catálogo versionable

Este directorio contendrá los registros normalizados que sí conviene versionar en Git.

Formato inicial previsto:

```text
catalog/norms.jsonl
```

Cada línea será un objeto JSON independiente. La base SQLite de cada instalación se podrá reconstruir a partir de este catálogo y luego completar con la sincronización de fuentes oficiales.

Los PDF no se almacenarán aquí; se descargarán a `storage/pdfs/` y cada registro conservará su URL oficial y SHA-256.
