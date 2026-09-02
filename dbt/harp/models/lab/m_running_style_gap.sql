{{ config(materialized='table') }}

with actual_entry as (
  select
    race_id,
    kettonum,
    held_date,
    held_year,
    jyo_cd,
    distance_m,
    surface,
    track_cd,
    race_level,
    result_order,
    is_place,
    running_style_cd as actual_running_style_cd,
    rank_4c as actual_rank_4c,
    corner4_pos as actual_corner4_pos
  from {{ ref('int_race_entry_enriched') }}
  where running_style_cd is not null
     or corner4_pos is not null
),

relative_style as (
  select
    race_id,
    kettonum,
    running_style_avg3,
    running_style as avg3_running_style_rounded,
    horse_corner4_avg3,
    corner4_rate_z,
    race_avg_corner4,
    race_stddev_corner4,
    num_past3_races
  from {{ ref('feat_race_relative_z') }}
  where running_style_avg3 is not null
     or horse_corner4_avg3 is not null
     or corner4_rate_z is not null
),

joined as (
  select
    ae.race_id,
    ae.kettonum,
    ae.held_date,
    ae.held_year,
    ae.jyo_cd,
    ae.distance_m,
    ae.surface,
    ae.track_cd,
    ae.race_level,
    ae.result_order,
    ae.is_place,
    ae.actual_running_style_cd,
    ae.actual_rank_4c,
    ae.actual_corner4_pos,
    rs.running_style_avg3,
    rs.avg3_running_style_rounded,
    rs.horse_corner4_avg3,
    rs.corner4_rate_z,
    rs.race_avg_corner4,
    rs.race_stddev_corner4,
    rs.num_past3_races
  from actual_entry ae
  inner join relative_style rs
    using (race_id, kettonum)
)

select
  race_id,
  kettonum,
  held_date,
  held_year,
  jyo_cd,
  distance_m,
  surface,
  track_cd,
  race_level,
  result_order,
  is_place,
  actual_running_style_cd,
  actual_rank_4c,
  actual_corner4_pos,
  running_style_avg3,
  avg3_running_style_rounded,
  horse_corner4_avg3,
  corner4_rate_z,
  race_avg_corner4,
  race_stddev_corner4,
  num_past3_races,
  actual_running_style_cd - running_style_avg3 as running_style_delta,
  abs(actual_running_style_cd - running_style_avg3) as running_style_abs_delta,
  case
    when avg3_running_style_rounded = actual_running_style_cd then 1
    else 0
  end as avg3_rounded_match_flag,
  actual_corner4_pos - horse_corner4_avg3 as corner4_avg_delta,
  abs(actual_corner4_pos - horse_corner4_avg3) as corner4_avg_abs_delta,
  case
    when race_stddev_corner4 is null or race_stddev_corner4 = 0 then null
    else (actual_corner4_pos - race_avg_corner4) / race_stddev_corner4
  end as actual_corner4_z,
  case
    when race_stddev_corner4 is null or race_stddev_corner4 = 0 then null
    else ((actual_corner4_pos - race_avg_corner4) / race_stddev_corner4) - corner4_rate_z
  end as corner4_z_delta,
  case
    when race_stddev_corner4 is null or race_stddev_corner4 = 0 then null
    else abs(((actual_corner4_pos - race_avg_corner4) / race_stddev_corner4) - corner4_rate_z)
  end as corner4_z_abs_delta
from joined
