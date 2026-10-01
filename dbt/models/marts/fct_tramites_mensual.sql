-- Trámites de turismos por mes, provincia, combustible, antigüedad, tipo de titular y
-- procedencia. La cifra es un recuento de trámites: un mismo coche puede aparecer
-- varias veces (una compraventa genera dos cambios de titularidad).
select
    cast(strftime(t.mes, '%Y%m') as integer) as fecha_id,
    t.tramite,
    t.cod_provincia as provincia_id,
    t.combustible_id,
    case
        when t.antiguedad_anios is null then 'sin_dato'
        when t.antiguedad_anios <= 2 then '0_2'
        when t.antiguedad_anios <= 5 then '3_5'
        when t.antiguedad_anios <= 9 then '6_9'
        when t.antiguedad_anios <= 14 then '10_14'
        when t.antiguedad_anios <= 19 then '15_19'
        else '20_o_mas'
    end as tramo_antiguedad,
    t.persona,
    t.procedencia,
    t.motivo_baja,
    cast(count(*) as integer) as tramites,
    -- Para calcular la antigüedad media sin perder exactitud al agregar.
    cast(sum(t.antiguedad_anios) as bigint) as suma_antiguedad_anios,
    cast(count(t.antiguedad_anios) as integer) as tramites_con_antiguedad
from {{ ref('int_dgt__turismos') }} as t
group by all
