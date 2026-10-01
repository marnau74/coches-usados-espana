{#-
    La serie histórica anual y las tablas mensuales de la DGT son dos publicaciones distintas
    de las mismas cifras: el total y los turismos de cada año deben coincidir.
-#}

with mensuales as (
    select
        year(mes) as anio,
        case when es_total then 'total' else grupo_vehiculo end as grupo_vehiculo,
        sum(valor) as valor
    from {{ ref('stg_dgt__tablas_mensuales') }}
    where tramite = 'transferencias' and ((es_total and lower(columna) = 'total') or grupo_vehiculo = 'turismos')
    group by all
),

historica as (
    select
        anio,
        grupo_vehiculo,
        valor
    from {{ ref('stg_dgt__series_historicas') }}
    where tramite = 'transferencias' and grupo_vehiculo in ('total', 'turismos')
)

select
    m.anio,
    m.grupo_vehiculo,
    m.valor as tablas_mensuales,
    h.valor as serie_historica
from mensuales as m
inner join historica as h on m.anio = h.anio and m.grupo_vehiculo = h.grupo_vehiculo
where m.valor <> h.valor
