# 0005 · Cuadrar los microdatos con las tablas oficiales de la DGT

- **Estado:** aceptada
- **Fecha:** 2026-10-01

## Contexto

Un fichero de 714 caracteres por línea y 69 campos sin cabecera se puede leer mal sin que nada
falle: basta un campo desplazado una posición. Hacía falta una prueba independiente de que las
cifras son correctas. La DGT publica cada año tablas estadísticas con los mismos trámites
agregados por mes y tipo de vehículo, calculadas por otro camino.

## Decisión

Tests estrictos de dbt que comparan los microdatos con esas tablas, mes a mes:

- **Cambios de titularidad de turismos** (tipos 40 y 7A, el mismo grupo que la DGT): margen
  del 0,5 %. En los 24 meses de 2024 y 2025 la diferencia máxima es del 0,13 %.
- **Furgonetas:** margen del 1 %, por un tipo de vehículo frontera con los camiones.
- **Bajas definitivas de turismos** (claves 3, 4 y 7): margen del 0,5 %. La baja temporal
  no cuenta en la tabla.
- La **serie histórica** y las tablas mensuales (dos publicaciones distintas de la DGT) deben dar
  el mismo total y los mismos turismos de cada año.
- Los meses con diferencia que la fuente no explica están en el seed `excepciones_cuadre`, **con
  su motivo**: mayo y diciembre de 2024 y octubre de 2025 (entre un 0,7 y un 2,8 % más de
  bajas en los microdatos). El test los excluye solo para ese mes.

Los grupos de tipo de vehículo (`seeds/tipos_vehiculo.csv`) se ajustaron contra la tabla oficial,
no a ojo: «todo terreno» (25) cuenta como furgoneta y el «vehículo mixto adaptable» (0G) como
camión.

## Alternativas descartadas

- **Subir la tolerancia hasta que pase:** ocultaría errores nuevos del mismo tamaño.
- **Comparar contra fuentes de terceros** (anuarios de asociaciones del sector): no son
  abiertas ni se pueden descargar y repetir cada mes.

## Consecuencias

- Los tests de cuadre solo pueden comparar los meses para los que la DGT ya ha publicado tabla
  (hoy, hasta diciembre de 2025). No hay tabla de matriculaciones: la DGT las publica con otro
  nombre de fichero que no se ha localizado, y queda como límite conocido.
- Si la DGT cambia el diseño del fichero o la clasificación de un tipo de vehículo, el cuadre
  falla antes que cualquier gráfica.
