{#-
    Hay un fichero por cada mes desde el inicio de la ventana hasta el último, para los tres
    tipos de trámite, y cada uno tiene filas. Un mes sin fichero falsearía las series.
-#}

with esperados as (
    select
        f.mes,
        t.tramite
    from {{ ref('dim_fecha') }} as f
    cross join (values ('matriculaciones'), ('transferencias'), ('bajas')) as t (tramite)
),

presentes as (
    select
        tramite,
        mes_fichero as mes,
        count(*) as filas
    from (
        select
            tramite,
            mes_fichero
        from {{ ref('stg_dgt__matriculaciones') }}
        union all
        select
            tramite,
            mes_fichero
        from {{ ref('stg_dgt__transferencias') }}
        union all
        select
            tramite,
            mes_fichero
        from {{ ref('stg_dgt__bajas') }}
    )
    group by all
)

select
    e.mes,
    e.tramite
from esperados as e
left join presentes as p on e.mes = p.mes and e.tramite = p.tramite
where coalesce(p.filas, 0) = 0
