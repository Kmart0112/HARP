-- The published NN current-entry relation must never expose entity identities,
-- outcomes, final odds, or lifecycle flags as accidental model inputs.
select column_name
from information_schema.columns
where table_schema = '{{ ref("m_nn_race_entry").schema }}'
  and table_name = '{{ ref("m_nn_race_entry").identifier }}'
  and column_name not in (
    {% for column in nn_pre_race_feature_columns() %}'{{ column }}',{% endfor %}
    'race_id', 'kettonum', 'held_date', 'history_end_no', 'last_history_race_id',
    'last_history_held_date', 'days_since_last_run', 'active_entrant_count',
    'monthly_stats_cutoff', 'yearly_stats_cutoff', 'jockey_stats_missing',
    'trainer_stats_missing', 'breeder_stats_missing', 'sire_stats_missing',
    'dam_stats_missing', 'damsire_stats_missing'
  )
