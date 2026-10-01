# 0002 · Dagster como orquestador

- **Estado:** aceptada
- **Fecha:** 2026-10-01

## Contexto

El pipeline tiene tres fuentes con ritmos distintos (microdatos mensuales de la DGT, tablas
anuales de la DGT, índices mensuales de Eurostat), una carga a bronze y una construcción de
silver y gold con dbt. Hay que poder ver el linaje completo, relanzar solo lo que cambia y
que un test de calidad fallido pare la publicación.

## Decisión

**Dagster con assets**: cada tabla o conjunto de ficheros es un asset y el orden sale de las
dependencias. Los modelos y seeds de dbt se cargan desde su manifest, así que el linaje va
de la descarga al mart final en un solo grafo. Un trabajo (`pipeline_mensual`) con programación
el día 20 de cada mes: la DGT y Eurostat publican el mes anterior hacia mediados de mes.

## Alternativas descartadas

- **Cron + scripts:** sin linaje ni comprobaciones registradas.
- **Airflow:** orientado a tareas, no a datos; más pesado de instalar para este tamaño.

## Consecuencias

- Dagster solo asigna como comprobación de un asset los tests de dbt ligados a un único
  modelo. Los de cuadre, que cruzan varios, corren igualmente dentro de `dbt build` y paran
  la ejecución si fallan; no aparecen en la interfaz de Dagster como comprobación de un asset.
- Los tests del grafo comprueban que cada capa depende de la anterior.
