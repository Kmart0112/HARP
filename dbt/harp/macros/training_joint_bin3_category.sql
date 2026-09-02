{% macro training_joint_bin3_category(haron_z_col, lap_z_col) -%}
  {%- set tertile_z = 0.4307273 -%}
  cast(
    case
      when {{ haron_z_col }} is null or {{ lap_z_col }} is null then 0
      else
        (
          (
            case
              when {{ haron_z_col }} <= -{{ tertile_z }} then 1
              when {{ haron_z_col }} <= {{ tertile_z }} then 2
              else 3
            end
            - 1
          ) * 3
        ) + (
          case
            when {{ lap_z_col }} <= -{{ tertile_z }} then 1
            when {{ lap_z_col }} <= {{ tertile_z }} then 2
            else 3
          end
        )
    end as integer
  )
{%- endmacro %}
