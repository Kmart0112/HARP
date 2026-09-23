select race_id, kettonum
from {{ ref('feat_race_entry_pre_race') }}
group by race_id, kettonum
having count(*) <> 1
