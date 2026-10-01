# 0006 · Precios solo como índice: no hay fuente abierta en euros

- **Estado:** aceptada
- **Fecha:** 2026-10-01

## Contexto

La pregunta natural sobre coches de segunda mano es «cuánto cuestan». No existe una fuente
oficial, abierta y descargable con el precio en euros de los coches de ocasión. Se revisaron:

| Fuente | Qué da | Por qué no |
|---|---|---|
| Portales de anuncios (coches.net, Wallapop, etc.) | Precios de oferta | Solo se pueden obtener rascando sus webs, lo que va contra sus condiciones de uso |
| Datasets de Kaggle o Zenodo | Anuncios de un día concreto | Una instantánea de 2020 o 2022, de un solo portal: no es una serie |
| Informes de asociaciones del sector | Precio medio | No son datos abiertos y no se pueden descargar de forma repetible |
| Orden HAC/1501/2025 (BOE) | Valor fiscal por modelo y año | Es el valor de referencia para el impuesto de transmisiones, no el precio de mercado; fija un tipo de depreciación, no mide el mercado |
| **Eurostat, IPCA (`prc_hicp_minr`, ECOICOP 2)** | **Índice de precios de coches de segunda mano, nuevos y total, mensual desde 2014** | **Sí: oficial, abierto, con API y actualizado cada mes** |

## Decisión

Se usa el **índice de precios de Eurostat** (base 2025 = 100): `07.1.1.2` automóviles de
segunda mano, `07.1.1.1` nuevos y el total de precios, para España y, de referencia, la zona euro.
El informe lo presenta como lo que es: cuánto cambian los precios, no cuánto cuesta un coche.

Un test comprueba que la variación anual que publica Eurostat coincide con la que sale de su
propio índice (margen de 0,15 puntos por el redondeo).

## Consecuencias

- El proyecto no inventa ni estima precios en euros. Si algún día existe una fuente abierta, se
  añade como una tabla más de gold.
- Se ha descartado a propósito generar datos sintéticos de precios «realistas».
