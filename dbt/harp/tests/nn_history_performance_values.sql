-- Public history must preserve the shared calculation, including missing values.
select h.race_id, h.kettonum
from {{ ref('m_nn_run_history') }} h
left join {{ ref('int_race_entry_metrics') }} m
  on h.race_id = m.race_id and h.kettonum = m.kettonum
where h.time_vs_avg is distinct from m.time_vs_avg
   or h.pos4_agari_synergy is distinct from m.pos4_agari_synergy
