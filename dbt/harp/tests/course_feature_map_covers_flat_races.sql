with seed_rows as (
  select
    jyo_cd,
    surface,
    track_cd,
    jyo_name,
    surface_name,
    track_cd_label,
    turn_direction,
    turn_direction_cd,
    course_variant,
    straight_distance_m,
    elevation_diff_m,
    has_slope,
    has_homestretch_slope,
    has_uphill_finish,
    slope_feature_ja,
    source_url
  from {{ ref('course_feature_map') }}
)

select
  r.race_id,
  r.jyo_cd,
  r.surface,
  r.track_cd
from {{ ref('fct_race') }} r
join seed_rows s
  on r.jyo_cd = s.jyo_cd
 and r.surface = s.surface
 and r.track_cd = s.track_cd
where r.held_date >= '2008-01-01'
  and (
    r.jyo_name is distinct from s.jyo_name
    or r.surface_name is distinct from s.surface_name
    or r.track_cd_label is distinct from s.track_cd_label
    or r.turn_direction is distinct from s.turn_direction
    or r.turn_direction_cd is distinct from s.turn_direction_cd
    or r.course_variant is distinct from s.course_variant
    or r.straight_distance_m is distinct from s.straight_distance_m
    or r.elevation_diff_m is distinct from s.elevation_diff_m
    or r.has_slope is distinct from s.has_slope
    or r.has_homestretch_slope is distinct from s.has_homestretch_slope
    or r.has_uphill_finish is distinct from s.has_uphill_finish
    or r.slope_feature_ja is distinct from s.slope_feature_ja
    or r.source_url is distinct from s.source_url
  )
