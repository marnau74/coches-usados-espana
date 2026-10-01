{#
    Staging común de los tres ficheros de microdatos de la DGT, que comparten diseño de
    registro: selecciona los campos que usa el proyecto, les pone nombre y los tipa. Las
    fechas que no son válidas quedan en null (los tests miden cuántas hay); los códigos se
    dejan como en la fuente y se traducen en intermediate.

    `mes_fichero` es el mes del fichero (export_mensual_<clave>_AAAAMM): es el mes en el
    que la DGT procesa el trámite y el que usan sus tablas estadísticas, aunque la fecha
    del trámite sea a veces de un mes anterior (ver docs/adr/0004-semantica-de-los-datos.md).
#}
{% macro stg_microdatos_dgt(tramite) %}
select
    '{{ tramite }}' as tramite,
    make_date(
        cast(regexp_extract(_fichero_origen, '_(\d{4})\d{2}\.zip$', 1) as integer),
        cast(regexp_extract(_fichero_origen, '_\d{4}(\d{2})\.zip$', 1) as integer),
        1
    ) as mes_fichero,
    cast(try_strptime(fec_tramite, '%d%m%Y') as date) as fecha_tramite,
    cast(try_strptime(fec_matricula, '%d%m%Y') as date) as fecha_matricula,
    cast(try_strptime(fec_prim_matriculacion, '%d%m%Y') as date) as fecha_primera_matriculacion,
    clave_tramite,
    cod_tipo,
    cod_propulsion_itv as cod_propulsion,
    categoria_vehiculo_electrico,
    marca_itv as marca,
    modelo_itv as modelo,
    cod_provincia_veh,
    cod_provincia_mat,
    ind_nuevo_usado,
    persona_fisica_juridica,
    renting,
    ind_baja_def,
    try_cast(cilindrada_itv as integer) as cilindrada,
    try_cast(kw_itv as decimal(8, 2)) as potencia_kw,
    try_cast(co2_itv as integer) as co2_g_km,
    nivel_emisiones_euro_itv as nivel_emisiones_euro,
    _fichero_origen,
    _linea
from {{ source('bronze', 'dgt_' ~ tramite) }}
{% endmacro %}
