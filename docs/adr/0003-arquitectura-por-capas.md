# 0003 · Arquitectura por capas (raw, bronze, silver, gold)

- **Estado:** aceptada
- **Fecha:** 2026-10-01

## Contexto

Cuando un dato sale raro hay que saber si lo trajo así la fuente o lo estropeó el proyecto.
Las fuentes cambian de formato sin avisar.

## Decisión

| Capa | Regla |
|---|---|
| **raw** | Lo descargado, tal cual (ZIP de la DGT, Excel, JSON-stat de Eurostat). Inmutable. |
| **bronze** | Una tabla por fuente, sin interpretar. Los microdatos se cortan por las posiciones del diseño oficial y se guardan como **texto recortado**: ni fechas ni números tipados. Cada fila lleva `_fichero_origen` y `_linea`. |
| **silver** | Staging (tipado: las fechas inválidas quedan en null y se miden) e intermediate (reglas de negocio: qué trámites cuentan, combustible, antigüedad, marca y modelo normalizados). |
| **gold** | Modelo en estrella con contrato (tipos fijados): lo único que se consume. |

Tipar en staging y no en bronze es deliberado: una fecha mal formada no hace fallar la carga,
sino un test que dice cuántas hay.

## Consecuencias

- Las reglas de negocio están en un solo sitio (`int_dgt__turismos`) y se pueden leer.
- Cualquier cifra de gold se puede seguir hasta la línea del fichero de la DGT de la que sale.
