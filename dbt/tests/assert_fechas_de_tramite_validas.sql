{#- Toda fila de microdatos tiene una fecha de trámite válida: sin ella no se sabría a qué mes pertenece. -#}

select
    tramite,
    mes_fichero,
    count(*) as filas_sin_fecha
from (
    select
        tramite,
        mes_fichero,
        fecha_tramite
    from {{ ref('stg_dgt__matriculaciones') }}
    union all
    select
        tramite,
        mes_fichero,
        fecha_tramite
    from {{ ref('stg_dgt__transferencias') }}
    union all
    select
        tramite,
        mes_fichero,
        fecha_tramite
    from {{ ref('stg_dgt__bajas') }}
)
where fecha_tramite is null
group by all
