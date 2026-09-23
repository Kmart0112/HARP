-- Test the shared semantic values rather than two separate implementations.
select m.race_id, m.kettonum
from {{ ref('m_race_entry_feature_matrix') }} m
left join {{ ref('feat_race_entry_pre_race') }} p using (race_id, kettonum)
where p.race_id is null or row({{ nn_select_pre_race_features('m') }})
  is distinct from row({{ nn_select_pre_race_features('p') }})
