{#-
    Los trámites anteriores a la ventana del proyecto son registros muy tardíos (la DGT
    incluye algunos de años anteriores) y se descartan. Si de pronto fuesen más del 2 %, algo
    habría cambiado en la fuente.
-#}

select
    tramite,
    anteriores,
    total,
    round(anteriores * 100.0 / total, 2) as pct
from (
    select
        tramite,
        count(*) filter (where fecha_tramite < date '{{ var("inicio_ventana") }}') as anteriores,
        count(*) as total
    from (
        select
            tramite,
            fecha_tramite
        from {{ ref('stg_dgt__matriculaciones') }}
        union all
        select
            tramite,
            fecha_tramite
        from {{ ref('stg_dgt__transferencias') }}
        union all
        select
            tramite,
            fecha_tramite
        from {{ ref('stg_dgt__bajas') }}
    )
    group by all
)
where anteriores * 1.0 / total > 0.02
