-- Cambios de titularidad por año y tipo de vehículo desde 1990 (serie histórica oficial
-- de la DGT). Camiones y furgonetas van juntos: así los publica la serie.
select
    s.anio,
    s.grupo_vehiculo,
    s.valor as cambios_titularidad
from {{ ref('stg_dgt__series_historicas') }} as s
where s.tramite = 'transferencias' and s.grupo_vehiculo <> 'total'
