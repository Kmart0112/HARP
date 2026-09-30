select race_id, kettonum
from {{ ref('feat_race_entry_opponent_summary') }}
where opp_count < 0 or opp_count is null
  {% for entity in ['horse', 'jockey'] %}
  or (opp_count > 0 and opp_{{ entity }}_place_coverage is null)
  or abs(opp_{{ entity }}_place_coverage * opp_count
         - round((opp_{{ entity }}_place_coverage * opp_count)::numeric)) > 1e-8
  or opp_{{ entity }}_place_top3_mean < opp_{{ entity }}_place_mean - 1e-10
  {% for suffix in ['place_mean', 'place_top3_mean', 'starts_mean'] + (['place_std'] if entity == 'horse' else []) %}
  or ((opp_{{ entity }}_{{ suffix }} is not null)
      is distinct from coalesce(opp_{{ entity }}_place_coverage > 0, false))
  {% endfor %}
  {% endfor %}
  {% for column in nn_history_context_columns() if column != 'opp_count' %}
  or (opp_count = 0 and {{ column }} is not null)
  or {{ column }} < -1e-10
  {% if '_place_' in column %}
  or {{ column }} > {{ 0.5 if column.endswith('_std') else 1 }} + 1e-10
  {% endif %}
  {% endfor %}
