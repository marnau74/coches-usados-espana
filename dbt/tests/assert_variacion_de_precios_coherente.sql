{#-
    La variación anual que publica Eurostat coincide con la que sale de su propio índice
    (margen de 0,15 puntos por el redondeo del índice a dos decimales).
-#}

select
    fecha_id,
    territorio,
    producto,
    variacion_anual,
    variacion_anual_calculada
from {{ ref('fct_precios_indice_mensual') }}
where
    variacion_anual is not null
    and variacion_anual_calculada is not null
    and abs(variacion_anual - variacion_anual_calculada) > 0.15
