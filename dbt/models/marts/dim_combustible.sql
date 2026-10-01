select
    combustible_id,
    nombre,
    orden,
    enchufable
from {{ ref('combustibles') }}
