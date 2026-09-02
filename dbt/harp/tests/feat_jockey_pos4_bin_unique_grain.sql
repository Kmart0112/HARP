select
  jockey_cd,
  held_year_month,
  pos4_bin5,
  count(*) as row_count
from {{ ref('feat_jockey_pos4_bin') }}
group by
  jockey_cd,
  held_year_month,
  pos4_bin5
having count(*) > 1
