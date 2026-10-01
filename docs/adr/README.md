# Decisiones de arquitectura

Cada decisión relevante queda registrada en un ADR corto: contexto, decisión,
alternativas descartadas y consecuencias. Un ADR no se edita cuando cambia la
decisión: se escribe uno nuevo que lo sustituye.

| Nº | Decisión | Estado |
|---|---|---|
| [0001](0001-duckdb-como-warehouse.md) | DuckDB como warehouse, con los microdatos en Parquet | Aceptada |
| [0002](0002-dagster-como-orquestador.md) | Dagster como orquestador | Aceptada |
| [0003](0003-arquitectura-por-capas.md) | Arquitectura por capas (raw, bronze, silver, gold) | Aceptada |
| [0004](0004-semantica-de-los-datos.md) | Qué cuenta cada cifra: trámites, mes de la fecha de trámite y provisionales | Aceptada |
| [0005](0005-cuadre-con-las-tablas-oficiales.md) | Cuadrar los microdatos con las tablas oficiales de la DGT | Aceptada |
| [0006](0006-precios-solo-como-indice.md) | Precios solo como índice: no hay fuente abierta en euros | Aceptada |
| [0007](0007-formato-de-los-ficheros-de-la-dgt.md) | Leer los ficheros de la DGT por su diseño de registro, y fallar si cambia | Aceptada |
