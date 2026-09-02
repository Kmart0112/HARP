select
  jyo_cd,
  surface,
  track_cd,
  count(*) as row_count
from {{ ref('course_feature_map') }}
group by 1, 2, 3
having count(*) > 1
