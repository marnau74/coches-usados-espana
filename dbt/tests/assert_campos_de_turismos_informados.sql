{#-
    Los campos que usan los análisis vienen informados en casi todos los turismos: la
    antigüedad y el combustible fallan en menos del 1 %, y no hay antigüedades imposibles.
-#}

select
    campo,
    sin_dato,
    total,
    round(sin_dato * 100.0 / total, 2) as pct
from (
    select
        'antiguedad' as campo,
        count(*) filter (where antiguedad_anios is null) as sin_dato,
        count(*) as total
    from {{ ref('int_dgt__turismos') }}
    union all
    select
        'combustible' as campo,
        count(*) filter (where combustible_id = 'desconocido') as sin_dato,
        count(*) as total
    from {{ ref('int_dgt__turismos') }}
    union all
    select
        'antiguedad_imposible' as campo,
        count(*) filter (where antiguedad_anios > 100) as sin_dato,
        count(*) as total
    from {{ ref('int_dgt__turismos') }}
)
where sin_dato * 1.0 / total > 0.01
