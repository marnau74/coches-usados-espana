{#- Un recuento de vehículos nunca puede ser negativo. -#}
{% test no_negativo(model, column_name) %}

select {{ column_name }}
from {{ model }}
where {{ column_name }} < 0

{% endtest %}
