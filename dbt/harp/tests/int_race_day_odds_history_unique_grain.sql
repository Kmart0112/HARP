select
  race_id,
  horse_number,
  snapshot_time_key,
  count(*) as row_count
from {{ ref('int_race_day_odds_history') }}
group by 1, 2, 3
having count(*) > 1
