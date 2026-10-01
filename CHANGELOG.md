# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versionado
[semántico](https://semver.org/lang/es/).

## [Sin publicar]

### Corregido
- Los reintentos con la DGT estaban en dos capas (la sesión HTTP y el cliente) que se multiplicaban:
  con el servidor caído, una ejecución tardaba casi una hora. Ahora solo reintenta el cliente, y sin
  listado los meses que quizá aún no existen se prueban solo dos veces.
- `release.py` borraba todo lo que hubiera en la carpeta de salida y sumaba cualquier fichero que
  encontrara en ella: ahora solo toca y suma los que genera.
- La documentación decía 100 comprobaciones de dbt; son 80 tests (el resto eran seeds y modelos).

### Cambiado
- `publicar` ya no se lanza con cualquier cambio en `main`, solo si afecta a los datos o al informe,
  y solo guarda una caché nueva (3 GB) cuando cambian los ficheros de la DGT, no en cada ejecución.

## [1.0.0] - 2026-10-01

Primera versión: plataforma de datos del mercado de coches de segunda mano en España con
datos oficiales.

### Añadido
- Ingesta real de los microdatos mensuales de **matriculaciones, transferencias y bajas de la
  DGT** (enero de 2024 en adelante, 23 millones de trámites), de sus tablas estadísticas anuales
  y del índice de precios de **Eurostat** (coches de segunda mano, nuevos y total).
- Arquitectura por capas (raw, bronze en Parquet, silver y gold con dbt) y orquestación con
  Dagster (ADR 0001–0003).
- Lectura de los ficheros de la DGT por su diseño de registro oficial (714 caracteres, 69
  campos, Latin-1), con validación de cada ZIP y reintentos (ADR 0007).
- Cuadre de los microdatos con las tablas oficiales de la DGT: cambios de titularidad de turismos
  con una diferencia máxima del 0,13 % en 24 meses (ADR 0005).
- Informe web con todas las cifras calculadas desde gold, documentación con el linaje de los datos
  y release mensual (`datos-AAAA-MM`) con Parquet, DuckDB, contrato y sumas SHA-256.
- 80 tests de dbt, 95 tests de Python y CI con datos sintéticos de formato idéntico al real.
