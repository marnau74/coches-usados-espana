-- Un mes por fila, del primero al último con trámites. Los dos últimos meses son
-- provisionales: la DGT sigue añadiendo trámites tardíos en los ficheros siguientes
-- (en el mes del fichero faltan ~3 % de los trámites; en el anterior, ~0,1 %).
with ultimo_fichero as (
    select max(mes_fichero) as mes
    from (
        select mes_fichero from {{ ref('stg_dgt__matriculaciones') }}
        union all
        select mes_fichero from {{ ref('stg_dgt__transferencias') }}
        union all
        select mes_fichero from {{ ref('stg_dgt__bajas') }}
    )
),

meses as (
    select
        unnest(
            generate_series(date '{{ var("inicio_ventana") }}', (select mes from ultimo_fichero), interval 1 month)
        )::date
            as mes
)

select
    cast(strftime(m.mes, '%Y%m') as integer) as fecha_id,
    m.mes,
    cast(year(m.mes) as smallint) as anio,
    cast(month(m.mes) as smallint) as mes_numero,
    cast(quarter(m.mes) as smallint) as trimestre,
    m.mes >= u.mes - interval 1 month as provisional
from meses as m
cross join ultimo_fichero as u
