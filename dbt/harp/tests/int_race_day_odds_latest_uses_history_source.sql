select
  odds_source,
  count(*) as row_count
from {{ ref('int_race_day_odds_latest') }}
where odds_source <> 'int_race_day_odds_history'
group by 1
