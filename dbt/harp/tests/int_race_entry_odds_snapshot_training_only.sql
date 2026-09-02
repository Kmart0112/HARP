select
  odds_snapshot_type,
  odds_source,
  count(*) as row_count
from {{ ref('int_race_entry_odds_snapshot') }}
where odds_snapshot_type <> 'pre10m'
   or odds_source <> 'published_manual.fct_jodds_snapshot'
group by 1, 2
