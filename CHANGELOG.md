# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versionado
[semántico](https://semver.org/lang/es/).

## [Sin publicar]

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
- 100 comprobaciones de dbt, 95 tests de Python y CI con datos sintéticos de formato idéntico al
  real.
