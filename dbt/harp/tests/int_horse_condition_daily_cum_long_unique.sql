select
  kettonum,
  held_date,
  condition_group,
  condition_key1,
  condition_key2
from {{ ref('int_horse_condition_daily_cum_long') }}
group by
  kettonum,
  held_date,
  condition_group,
  condition_key1,
  condition_key2
having count(*) > 1
