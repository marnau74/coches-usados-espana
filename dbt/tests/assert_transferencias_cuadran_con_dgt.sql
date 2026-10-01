{#-
    Los cambios de titularidad de los microdatos (por fecha de trámite) cuadran con la tabla
    oficial «V.2» de la DGT: turismos (margen del 0,5 %) y furgonetas (1 %, porque hay un tipo
    de vehículo frontera entre furgonetas y camiones), mes a mes. Los
    grupos de tipo de vehículo son los de seeds/tipos_vehiculo.csv (la DGT cuenta las
    autocaravanas, tipo 7A, como turismos); si la agrupación fuese otra, este test fallaría.
    Solo se comparan los meses para los que la DGT ya ha publicado tabla.
-#}

with micro as (
    select
        date_trunc('month', t.fecha_tramite)::date as mes,
        v.grupo as grupo_vehiculo,
        count(*) as tramites
    from {{ ref('stg_dgt__transferencias') }} as t
    inner join {{ ref('tipos_vehiculo') }} as v on t.cod_tipo = v.cod_tipo
    where t.clave_tramite = '2' and v.grupo in ('turismos', 'furgonetas')
    group by all
),

oficial as (
    select
        mes,
        grupo_vehiculo,
        valor as tramites
    from {{ ref('stg_dgt__tablas_mensuales') }}
    where tramite = 'transferencias' and grupo_vehiculo in ('turismos', 'furgonetas') and not es_total
)

select
    o.mes,
    o.grupo_vehiculo,
    o.tramites as oficial,
    m.tramites as microdatos,
    round((m.tramites - o.tramites) * 100.0 / o.tramites, 3) as diferencia_pct
from oficial as o
left join micro as m on o.mes = m.mes and o.grupo_vehiculo = m.grupo_vehiculo
where
    m.tramites is null
    or abs(m.tramites - o.tramites) * 1.0 / o.tramites > case o.grupo_vehiculo when 'turismos' then 0.005 else 0.01 end
