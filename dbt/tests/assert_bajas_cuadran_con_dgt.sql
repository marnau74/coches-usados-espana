{#-
    Las bajas definitivas de turismos de los microdatos (claves de trámite 3, 4 y 7) cuadran
    con la tabla oficial «V.3» de la DGT, mes a mes, con un 0,5 % de margen. La baja temporal
    (clave 6) no cuenta en la tabla. Los meses en que la DGT no explica la diferencia están
    en seeds/excepciones_cuadre.csv.
-#}

with micro as (
    select
        date_trunc('month', fecha_tramite)::date as mes,
        count(*) as tramites
    from {{ ref('stg_dgt__bajas') }}
    where cod_tipo = '40' and clave_tramite in ('3', '4', '7')
    group by all
),

oficial as (
    select
        mes,
        valor as tramites
    from {{ ref('stg_dgt__tablas_mensuales') }}
    where tramite = 'bajas' and grupo_vehiculo = 'turismos' and not es_total
)

select
    o.mes,
    o.tramites as oficial,
    m.tramites as microdatos,
    round((m.tramites - o.tramites) * 100.0 / o.tramites, 3) as diferencia_pct
from oficial as o
left join micro as m on o.mes = m.mes
where
    (m.tramites is null or abs(m.tramites - o.tramites) * 1.0 / o.tramites > 0.005)
    and strftime(o.mes, '%Y-%m') not in (
        select e.mes from {{ ref('excepciones_cuadre') }} as e
        where e.prueba = 'bajas_turismos'
    )
