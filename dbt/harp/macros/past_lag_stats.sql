{% macro lag_count_nonnull(columns) %}
  (
  {%- for column in columns %}
    (case when {{ column }} is null then 0 else 1 end){% if not loop.last %} +{% endif %}
  {%- endfor -%}
  )
{% endmacro %}

{% macro lag_avg(columns) %}
  (
  {%- for column in columns %}
    coalesce({{ column }}, 0){% if not loop.last %} +{% endif %}
  {%- endfor -%}
  ) / nullif({{ lag_count_nonnull(columns) }}, 0)
{% endmacro %}

{% macro lag_weighted_avg(weighted_columns) %}
  (
  {%- for item in weighted_columns %}
    (case when {{ item[0] }} is null then 0 else {{ item[0] }} * {{ item[1] }} end){% if not loop.last %} +{% endif %}
  {%- endfor -%}
  ) / nullif(
    (
    {%- for item in weighted_columns %}
      (case when {{ item[0] }} is null then 0 else {{ item[1] }} end){% if not loop.last %} +{% endif %}
    {%- endfor -%}
    ),
    0
  )
{% endmacro %}

{% macro lag_stddev_sample(columns) %}
  {%- set count_expr -%}
    {{ lag_count_nonnull(columns) }}
  {%- endset -%}
  {%- set variance_expr -%}
    (
      (
      {%- for column in columns %}
        (case when {{ column }} is null then 0 else power({{ column }}, 2) end){% if not loop.last %} +{% endif %}
      {%- endfor -%}
      )
      -
      power(
        (
        {%- for column in columns %}
          coalesce({{ column }}, 0){% if not loop.last %} +{% endif %}
        {%- endfor -%}
        ),
        2
      )::float / nullif({{ count_expr }}, 0)
    )
    /
    nullif({{ count_expr }} - 1, 0)
  {%- endset -%}
  case
    when {{ count_expr }} <= 1 then null
    when {{ variance_expr }} between -1e-12 and 0 then 0
    else sqrt({{ variance_expr }})
  end
{% endmacro %}

{% macro lag_trend(first_column, last_column, steps) %}
  case
    when {{ first_column }} is null or {{ last_column }} is null then null
    else ({{ last_column }} - {{ first_column }})::float / {{ steps }}
  end
{% endmacro %}
