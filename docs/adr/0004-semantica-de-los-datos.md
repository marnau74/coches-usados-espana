# 0004 · Qué cuenta cada cifra

- **Estado:** aceptada
- **Fecha:** 2026-10-01

## Contexto

Los microdatos de la DGT son el registro de trámites, no un registro de ventas. Interpretarlos
mal da cifras que parecen razonables y no lo son. Estas son las decisiones que más cambian
los números, todas comprobadas con los datos reales.

## Decisión

**Se cuentan trámites, no coches.** Una compraventa con concesionario genera dos cambios de
titularidad. Un cambio de titularidad tampoco es siempre una venta (herencias, donaciones).
Por eso las cifras se llaman «cambios de titularidad» y nunca «ventas».

**«Turismo» es el tipo 40 de la DGT.** Quedan fuera furgonetas, todoterrenos (tipo 25),
autocaravanas (7A) y motos. En sus tablas, la DGT cuenta el tipo 7A como turismo (+0,6 %):
el cuadre lo tiene en cuenta (ADR 0005), pero el análisis no.

**Solo los trámites que cambian el parque o la propiedad:** matriculación ordinaria (clave 1),
cambio de titularidad (2) y baja definitiva (3, 4 y 7). Fuera: rematriculaciones, matrículas
temporales y la baja temporal (6), que no saca el coche del parque.

**Un trámite pertenece al mes de su fecha de trámite**, no al del fichero que lo trae. La DGT
incluye en cada fichero trámites tardíos: en el de junio de 2025 hay 65.669 turismos fechados
en abril, y el fichero de abril tiene un 21 % menos de lo que cuenta su tabla oficial. Contar
por fichero falsea los meses; contar por fecha de trámite cuadra con la tabla de la DGT.

**Los dos últimos meses son provisionales.** En un mes ya cerrado, el 3,2 % de los cambios de
titularidad llegó en un fichero posterior al de su mes. `dim_fecha.provisional` lo marca y el
informe lo dibuja.

**Los trámites anteriores a enero de 2024 se descartan** (20.810 transferencias y 50.000 bajas
de todos los tipos de vehículo, un 0,2 % y un 0,8 %): son registros muy tardíos, de meses que
el proyecto no cubre. Un test avisa si superan el 2 %.

**Las bajas se separan por motivo.** En febrero de 2024 hay 520.708 bajas de turismos con motivo
«4 · otros motivos», concentradas en tres días. La tabla oficial de la DGT también las recoge,
así que se mantienen, pero aparte: mezcladas con las voluntarias harían parecer que en 2024 se
dieron de baja casi el doble de coches.

**Combustible:** la categoría de vehículo eléctrico (BEV, PHEV, HEV…) manda sobre el código de
propulsión, porque un híbrido figura en el registro como gasolina o diésel.

**Modelo:** se agrupa por familia (primera palabra, sin la marca delante ni la versión), con
dos reglas propias (series de BMW, clases de Mercedes) y un alias de marca (MERCEDES →
MERCEDES-BENZ). Es una aproximación y está dicha: algunas denominaciones comerciales se reparten
en dos nombres en el registro.

## Consecuencias

- Las cifras no se pueden comparar con las de fuentes que cuenten ventas o por fecha de fichero.
- Ninguna de estas reglas es opinable en silencio: cada una tiene un test.
