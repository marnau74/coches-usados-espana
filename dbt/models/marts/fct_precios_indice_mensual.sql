-- Índice de precios de consumo armonizado (Eurostat, base 2025 = 100) de automóviles de
-- segunda mano, nuevos y del conjunto de bienes y servicios, para España y la zona euro.
-- No es un precio en euros: mide cómo cambian los precios. `variacion_anual` es la que
-- publica Eurostat; `variacion_anual_calculada` sale del índice y sirve de control.
with indices as (
    select
        territorio,
        producto,
        mes,
        valor as indice
    from {{ ref('stg_eurostat__series') }}
    where medida = 'indice'
),

tasas as (
    select
        territorio,
        producto,
        mes,
        valor as variacion_anual
    from {{ ref('stg_eurostat__series') }}
    where medida = 'tasa_anual'
)

select
    cast(strftime(i.mes, '%Y%m') as integer) as fecha_id,
    i.territorio,
    i.producto,
    i.indice,
    t.variacion_anual,
    round((i.indice / lag(i.indice, 12) over (partition by i.territorio, i.producto order by i.mes) - 1) * 100, 1)
        as variacion_anual_calculada
from indices as i
left join tasas as t on i.territorio = t.territorio and i.producto = t.producto and i.mes = t.mes
