{{ config(materialized='table') }}

{#-
    Un trámite por fila, solo turismos (cod_tipo 40) y solo los trámites que cuentan en
    este proyecto:
      - matriculacion:  matriculación ordinaria (clave 1). Fuera: rematriculaciones,
                        matrículas temporales y pasos de temporal a definitiva.
      - transferencia:  cambio de titularidad (clave 2).
      - baja:           baja definitiva (claves 3, 4 y 7). Fuera: la baja temporal (clave 6),
                        que no saca el coche del parque.
    El mes del trámite es el de su fecha de trámite, no el del fichero en el que llega:
    la DGT incluye en un fichero trámites tardíos de meses anteriores (en el de junio
    de 2025, 65.669 turismos fechados en abril) y sus tablas cuentan por fecha de trámite.
    Los trámites anteriores a la ventana del proyecto (2024-01) se descartan; son los
    registros tardíos de más de un mes y se cuentan en el test assert_tramites_fuera_de_ventana.
-#}

with tramites as (
    select * from {{ ref('stg_dgt__matriculaciones') }}
    where clave_tramite = '1'
    union all by name
    select * from {{ ref('stg_dgt__transferencias') }}
    where clave_tramite = '2'
    union all by name
    select * from {{ ref('stg_dgt__bajas') }}
    where clave_tramite in ('3', '4', '7')
),

turismos as (
    select
        * replace (
            case tramite
                when 'matriculaciones' then 'matriculacion' when 'transferencias' then 'transferencia' else 'baja'
            end as tramite
        ),
        date_trunc('month', fecha_tramite)::date as mes,
        -- Años cumplidos desde la matriculación. La fecha de primera matriculación viene
        -- vacía en el 93 % de las filas; la de matrícula siempre está.
        case
            when fecha_matricula is null or fecha_matricula > fecha_tramite then null
            else floor(date_diff('day', fecha_matricula, fecha_tramite) / 365.25)::integer
        end as antiguedad_anios,
        upper(trim(marca)) as marca_original
    from tramites
    where cod_tipo = '40' and fecha_tramite >= date '{{ var("inicio_ventana") }}'
)

select
    t.mes,
    t.mes_fichero,
    t.tramite,
    t.fecha_tramite,
    t.antiguedad_anios,
    t.cilindrada,
    t.potencia_kw,
    t.co2_g_km,
    t.cod_propulsion,
    t.ind_baja_def,
    -- Provincia del domicilio del vehículo; sin dato queda como desconocida (DS).
    coalesce(t.cod_provincia_veh, 'DS') as cod_provincia,
    case t.persona_fisica_juridica when 'D' then 'fisica' when 'X' then 'juridica' else 'desconocida' end as persona,
    case
        when t.tramite <> 'matriculacion' then 'no_aplica'
        when t.ind_nuevo_usado = 'N' then 'nuevo'
        when t.ind_nuevo_usado = 'U' then 'usado_importado'
        else 'no_aplica'
    end as procedencia,
    -- Combustible: la categoría eléctrica (HEV, PHEV...) manda sobre el código de propulsión,
    -- porque un híbrido figura como gasolina o diésel en este.
    case
        when t.categoria_vehiculo_electrico in ('BEV', 'FCEV') then 'electrico'
        when t.categoria_vehiculo_electrico in ('PHEV', 'REEV') then 'hibrido_enchufable'
        when t.categoria_vehiculo_electrico = 'HEV' then 'hibrido'
        when t.cod_propulsion = '0' then 'gasolina'
        when t.cod_propulsion = '1' then 'diesel'
        when t.cod_propulsion = '2' then 'electrico'
        when t.cod_propulsion in ('4', '6', '7', '8') then 'gas'
        when t.cod_propulsion is null then 'desconocido'
        else 'otros'
    end as combustible_id,
    -- Motivo de la baja definitiva según el código de la DGT (anexo I, IND_BAJA_DEF). El 4
    -- («otros motivos») se separa porque en febrero de 2024 acumula 520.000 bajas en tres días.
    case
        when t.tramite <> 'baja' then 'no_aplica'
        when t.ind_baja_def = '7' then 'voluntaria'
        when t.ind_baja_def in ('0', '1', '2', '3', '5', 'C') then 'desguace'
        when t.ind_baja_def in ('A', 'B') then 'de_oficio'
        when t.ind_baja_def in ('8', '9') then 'exportacion'
        else 'otros_motivos'
    end as motivo_baja,
    t.marca,
    -- Familia del modelo, sin la marca delante («NISSAN QASHQAI» → «QASHQAI»), sin «NUEVO»
    -- («NUEVO C3» → «C3») y sin la cilindrada o versión que el registro pega al nombre
    -- («GOLF 1.9 TDI» → «GOLF»). Las series de BMW (320D, 118D...) y las clases de Mercedes
    -- («CLASE C» y «C 220 D») se unen en una sola.
    nullif(
        case
            when
                t.marca = 'BMW' and regexp_matches(t.modelo_base, '^[1-8][0-9]{2}[A-Z]*( |$)')
                then 'SERIE ' || substr(t.modelo_base, 1, 1)
            when
                regexp_matches(t.modelo_base, '^SERIE ?[0-9]')
                then 'SERIE ' || regexp_extract(t.modelo_base, '^SERIE ?([0-9])', 1)
            when regexp_matches(t.modelo_base, '^CLASE [^ ]') then regexp_extract(t.modelo_base, '^CLASE ([^ ]+)', 1)
            else regexp_extract(t.modelo_base, '^[^ ]+')
        end,
        ''
    ) as modelo
from (
    select
        b.*,
        regexp_replace(
            ltrim(
                regexp_replace(
                    upper(trim(b.modelo_sin_normalizar)),
                    '^' || regexp_replace(b.marca, '[^A-Z0-9 ]', '.', 'g') || '[ -]*',
                    ''
                )
            ),
            '^(NUEVO|NUEVA|NEW) ', ''
        ) as modelo_base
    from (
        select
            tt.* exclude (marca),
            coalesce(a.marca, tt.marca_original) as marca,
            tt.modelo as modelo_sin_normalizar
        from turismos as tt
        left join {{ ref('marcas_alias') }} as a on tt.marca_original = a.alias
    ) as b
) as t
