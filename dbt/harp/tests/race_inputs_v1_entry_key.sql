select race_id, horse_number
from {{ ref('m_training_inputs_v1') }}
where not is_scratched
group by race_id, horse_number
having count(*) <> 1

