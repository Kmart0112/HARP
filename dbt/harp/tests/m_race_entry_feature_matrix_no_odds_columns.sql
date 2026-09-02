select column_name
from information_schema.columns
where table_schema = '{{ ref("m_race_entry_feature_matrix").schema }}'
  and table_name = '{{ ref("m_race_entry_feature_matrix").identifier }}'
  and column_name in (
    'feature_snapshot_type',
    'odds_snapshot_type',
    'snapshot_at',
    'popularity',
    'popularity_ratio',
    'odds_tansho',
    'j_odds_tansho',
    'log_odds_tansho',
    'odds_fukusho_low',
    'odds_fukusho_high',
    'odds_fukusho_avg',
    'odds_fukusho_weighted_avg',
    'odds_source'
  )
