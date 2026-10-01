# 0001 · DuckDB como warehouse, con los microdatos en Parquet

- **Estado:** aceptada
- **Fecha:** 2026-10-01

## Contexto

Los microdatos de la DGT son 23 millones de trámites en 32 meses (unos 2 GB en ZIP y 16 GB
de texto de ancho fijo). Hace falta consultarlos con SQL, cruzarlos con tablas pequeñas y
que cualquiera pueda reproducir el proyecto sin un servidor.

## Decisión

- **DuckDB** como warehouse: un fichero, sin servidor, lee Parquet directamente y agrega
  decenas de millones de filas en segundos (`dbt build` completo: ~20 s con los datos reales).
- Los microdatos se guardan en **bronze como un Parquet por mes y tipo de trámite**, y el
  warehouse los ve con una vista. Un mes ya convertido no se rehace salvo que su ZIP sea más
  nuevo. El warehouse pesa megabytes; los datos, un GB de Parquet comprimido con zstd.
- Las tablas pequeñas (tablas oficiales de la DGT, Eurostat) se reemplazan enteras en cada carga.

## Alternativas descartadas

- **Cargar las 23 millones de filas en una tabla de DuckDB:** funciona, pero cada reproceso
  de un mes obligaría a reescribir la tabla entera y el fichero crecería sin necesidad.
- **PostgreSQL o un warehouse en la nube:** exigen un servidor o una cuenta para un proyecto
  cuyo valor no está en la infraestructura.

## Consecuencias

- Las vistas de bronze guardan la ruta de los Parquet: el warehouse y la carpeta `data/bronze/`
  van juntos.
- La CI no puede descargar 2 GB en cada cambio: usa ficheros sintéticos con el formato exacto
  de las fuentes (`tests/sinteticos.py`) y el pipeline real corre una vez al mes.
