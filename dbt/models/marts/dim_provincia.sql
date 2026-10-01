select
    codigo_dgt as provincia_id,
    provincia,
    comunidad,
    codigo_ine
from {{ ref('provincias') }}
