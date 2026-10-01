-- Trámites de turismos por marca y modelo (familia) y mes, solo matriculaciones y cambios
-- de titularidad. Los modelos con menos de 12 trámites en todo el periodo se agrupan
-- como «OTROS» (el registro tiene miles de variantes con muy pocos coches).
with por_modelo as (
    select
        cast(strftime(mes, '%Y%m') as integer) as fecha_id,
        tramite,
        marca,
        coalesce(modelo, 'SIN MODELO') as modelo,
        cast(count(*) as integer) as tramites,
        cast(sum(antiguedad_anios) as bigint) as suma_antiguedad_anios,
        cast(count(antiguedad_anios) as integer) as tramites_con_antiguedad
    from {{ ref('int_dgt__turismos') }}
    where tramite in ('matriculacion', 'transferencia')
    group by all
),

totales as (
    select
        marca,
        modelo,
        sum(tramites) as total
    from por_modelo
    group by all
)

select
    p.fecha_id,
    p.tramite,
    p.marca,
    case when t.total >= 12 then p.modelo else 'OTROS' end as modelo,
    cast(sum(p.tramites) as integer) as tramites,
    cast(sum(p.suma_antiguedad_anios) as bigint) as suma_antiguedad_anios,
    cast(sum(p.tramites_con_antiguedad) as integer) as tramites_con_antiguedad
from por_modelo as p
inner join totales as t on p.marca = t.marca and p.modelo = t.modelo
group by all
