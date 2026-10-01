{#
    Usa el esquema configurado tal cual (silver, gold, ref) en lugar del prefijo por
    defecto de dbt (<target>_<esquema>): las capas se llaman igual en todos los
    entornos, también en Databricks.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}{{ target.schema }}{%- else -%}{{ custom_schema_name | trim }}{%- endif -%}
{%- endmacro %}
