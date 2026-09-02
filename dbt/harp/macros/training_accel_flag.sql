{% macro training_accel_flag(lap_cols) -%}
  {%- if lap_cols | length < 2 -%}
    null
  {%- else -%}
    case
      when {{ lap_cols[0] }} is null then null
      when {{ lap_cols[1] }} is null then null
      {%- for idx in range(2, lap_cols | length) %}
      when {{ lap_cols[idx] }} is null then
        case
          when
            {%- for cmp_idx in range(idx - 1, 0, -1) %}
              {{ lap_cols[cmp_idx] }} >= {{ lap_cols[cmp_idx - 1] }}{% if not loop.last %} and {% endif %}
            {%- endfor %}
          then 1
          else 0
        end
      {%- endfor %}
      else
        case
          when
            {%- for cmp_idx in range((lap_cols | length) - 1, 0, -1) %}
              {{ lap_cols[cmp_idx] }} >= {{ lap_cols[cmp_idx - 1] }}{% if not loop.last %} and {% endif %}
            {%- endfor %}
          then 1
          else 0
        end
    end
  {%- endif -%}
{%- endmacro %}
