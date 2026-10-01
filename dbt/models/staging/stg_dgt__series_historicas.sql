-- Serie histórica anual de la DGT por tipo de vehículo, con los grupos del proyecto.
-- La DGT agrupa aquí camiones y furgonetas en una sola columna, y algunas cabeceras
-- llevan pegado el número de una nota al pie («Otros vehículos2»): se quita.
select
    s.tramite,
    s.anio,
    s.columna,
    s.valor,
    case regexp_replace(lower(s.columna), '[0-9]+$', '')
        when 'camiones y furgonetas' then 'camiones_y_furgonetas'
        when 'autobuses' then 'autobuses'
        when 'turismos' then 'turismos'
        when 'motocicletas' then 'motocicletas'
        when 'tractores industriales' then 'tractores_industriales'
        when 'remolques y semirremolques' then 'remolques'
        when 'otros vehículos' then 'otros'
        when 'total' then 'total'
    end as grupo_vehiculo,
    s._fichero_origen
from {{ source('bronze', 'dgt_series_historicas') }} as s
