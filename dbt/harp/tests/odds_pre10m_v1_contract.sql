select race_id, horse_number
from {{ ref('int_odds_pre10m_v1') }}
group by race_id, horse_number
having count(*) <> 1 or bool_or(odds_published_at > cutoff_at)

