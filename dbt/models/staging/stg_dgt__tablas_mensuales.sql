-- Tablas oficiales de la DGT por mes y tipo, con la columna publicada traducida a los
-- grupos de vehículo del proyecto. Las columnas de totales se marcan para no sumarlas.
select
    t.tramite,
    t.columna,
    t.valor,
    make_date(t.anio, t.mes, 1) as mes,
    case regexp_replace(lower(t.columna), '[0-9]+$', '')
        when 'camiones' then 'camiones'
        when 'furgonetas' then 'furgonetas'
        when 'autobuses' then 'autobuses'
        when 'turismos' then 'turismos'
        when 'motocicletas' then 'motocicletas'
        when 'tractores industriales' then 'tractores_industriales'
        when 'remolques y semirremolques' then 'remolques'
        when 'otros vehículos' then 'otros'
        when 'ciclomotores' then 'ciclomotores'
    end as grupo_vehiculo,
    lower(t.columna) in ('total', 'total general') as es_total,
    t._fichero_origen
from {{ source('bronze', 'dgt_tablas_mensuales') }} as t
