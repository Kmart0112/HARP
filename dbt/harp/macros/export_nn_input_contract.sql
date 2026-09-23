{% macro export_nn_input_contract() %}
  {# Machine-readable allowlist; Python must not maintain another copy by hand. #}
  {% set categories = [
    'sex_cd', 'blinker_cd', 'jyo_cd', 'surface', 'surface_condition_cd', 'weather_cd',
    'old_cd', 'race_level', 'grade_cd', 'track_cd', 'turn_direction_cd',
    'has_homestretch_slope', 'ensei_type'
  ] %}
  {% set fields = [] %}
  {% for name in nn_pre_race_feature_columns() %}
    {% do fields.append({'name': name, 'kind': 'categorical' if name in categories else 'numeric'}) %}
  {% endfor %}
  {% set results = [] %}
  {% for name in ['result_status_code', 'result_order', 'time_sec', 'time_diff', 'agari3f',
                 'rank_1c', 'rank_2c', 'rank_3c', 'rank_4c', 'running_style_cd'] %}
    {% do results.append({'name': name, 'kind': 'categorical' if name in ['result_status_code', 'running_style_cd'] else 'numeric'}) %}
  {% endfor %}
  {{ log(tojson({'version': 1, 'pre_race': fields, 'history_results': results}), info=True) }}
{% endmacro %}
