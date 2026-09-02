select
  race_id,
  horse_number,
  count(*) as row_count
from {{ ref('fct_race_entry_final_odds') }}
group by 1, 2
having count(*) > 1
