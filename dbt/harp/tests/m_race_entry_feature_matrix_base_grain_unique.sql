select
  race_id,
  kettonum,
  count(*) as row_count
from {{ ref('m_race_entry_feature_matrix') }}
group by 1, 2
having count(*) > 1
