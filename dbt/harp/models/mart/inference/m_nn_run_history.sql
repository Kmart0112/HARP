{{ config(materialized='view', tags=['nn_inputs', 'nn_history']) }}

-- Public history outlet. Preserve the upstream run keys, sequence and masks.
select
  r.*,
  {% for column in nn_history_context_columns() %}
  o.{{ column }}{% if not loop.last %},{% endif %}
  {% endfor %}
from {{ ref('int_race_entry_run_record') }} r
left join {{ ref('feat_race_entry_opponent_summary') }} o
  on r.race_id = o.race_id and r.kettonum = o.kettonum
  and r.held_date = o.held_date
