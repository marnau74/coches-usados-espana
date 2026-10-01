-- Series de Eurostat con sus dimensiones del catálogo y el mes como fecha.
select
    c.territorio,
    c.producto,
    c.medida,
    s.valor,
    s.estado,
    s.actualizado_en_fuente,
    s.id_serie,
    cast(strptime(s.periodo, '%Y-%m') as date) as mes,
    s._fichero_origen
from {{ source('bronze', 'eurostat_series') }} as s
inner join {{ ref('series_eurostat') }} as c on s.id_serie = c.id
