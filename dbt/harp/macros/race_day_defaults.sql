{% macro target_held_date_expr() -%}
  {%- if var('target_held_date', none) is not none -%}
    '{{ var("target_held_date") }}'::date
  {%- else -%}
    current_date
  {%- endif -%}
{%- endmacro %}
