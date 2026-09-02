select
  race_id,
  horse_number,
  count(*) as row_count
from {{ ref('int_race_day_odds_latest') }}
group by 1, 2
having count(*) > 1
