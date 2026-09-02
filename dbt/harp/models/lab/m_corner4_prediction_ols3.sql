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
    num_starters,
    corner4_pos as actual_corner4_pos
  from {{ ref('int_race_entry_enriched') }}
  where corner4_pos is not null
    and race_level in (1, 2, 3)
),

lag_base as (
  select
    race_id,
    kettonum,
    p1_corner4,
    p2_corner4,
    p3_corner4
  from {{ ref('int_race_entry_past_lag_base') }}
),

lag_features as (
  select
    race_id,
    kettonum,
    num_past3_races,
    horse_corner4_avg3
  from {{ ref('feat_race_entry_past_lag') }}
),

target_rows as (
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
    ae.num_starters,
    ae.actual_corner4_pos,
    lb.p1_corner4,
    lb.p2_corner4,
    lb.p3_corner4,
    lf.num_past3_races,
    lf.horse_corner4_avg3
  from actual_entry ae
  inner join lag_base lb
    using (race_id, kettonum)
  inner join lag_features lf
    using (race_id, kettonum)
),

scored_rows as (
  select
    tr.race_id,
    tr.kettonum,
    tr.held_date,
    tr.held_year,
    tr.jyo_cd,
    tr.distance_m,
    tr.surface,
    tr.track_cd,
    tr.race_level,
    tr.result_order,
    tr.is_place,
    tr.num_starters,
    tr.actual_corner4_pos,
    tr.p1_corner4,
    tr.p2_corner4,
    tr.p3_corner4,
    tr.num_past3_races,
    tr.horse_corner4_avg3,
    (
      case when tr.p1_corner4 is not null then 1 else 0 end +
      case when tr.p2_corner4 is not null then 1 else 0 end +
      case when tr.p3_corner4 is not null then 1 else 0 end
    ) as ols3_points,
    case
      when tr.p1_corner4 is not null and tr.p2_corner4 is not null and tr.p3_corner4 is not null
        then (tr.p1_corner4 - tr.p3_corner4)::float / 2.0
      when tr.p1_corner4 is not null and tr.p2_corner4 is not null
        then (tr.p1_corner4 - tr.p2_corner4)::float
      when tr.p2_corner4 is not null and tr.p3_corner4 is not null
        then (tr.p2_corner4 - tr.p3_corner4)::float
      when tr.p1_corner4 is not null and tr.p3_corner4 is not null
        then (tr.p1_corner4 - tr.p3_corner4)::float / 2.0
      else null
    end as ols3_slope,
    case
      when tr.p1_corner4 is not null and tr.p2_corner4 is not null and tr.p3_corner4 is not null
        then (4.0 * tr.p3_corner4 + tr.p2_corner4 - 2.0 * tr.p1_corner4) / 3.0
      when tr.p1_corner4 is not null and tr.p2_corner4 is not null
        then 3.0 * tr.p2_corner4 - 2.0 * tr.p1_corner4
      when tr.p2_corner4 is not null and tr.p3_corner4 is not null
        then 2.0 * tr.p3_corner4 - tr.p2_corner4
      when tr.p1_corner4 is not null and tr.p3_corner4 is not null
        then (3.0 * tr.p3_corner4 - tr.p1_corner4) / 2.0
      else null
    end as ols3_intercept
  from target_rows tr
)

select
  sr.race_id,
  sr.kettonum,
  sr.held_date,
  sr.held_year,
  sr.jyo_cd,
  sr.distance_m,
  sr.surface,
  sr.track_cd,
  sr.race_level,
  sr.result_order,
  sr.is_place,
  sr.num_starters,
  sr.actual_corner4_pos,
  sr.p1_corner4,
  sr.p2_corner4,
  sr.p3_corner4,
  sr.num_past3_races,
  sr.horse_corner4_avg3,
  sr.ols3_points,
  sr.ols3_slope,
  sr.ols3_intercept,
  least(greatest(sr.p1_corner4, 0), 1) as pred_last1,
  least(greatest(sr.horse_corner4_avg3, 0), 1) as pred_avg3,
  least(
    greatest(
      (
        (case when sr.p1_corner4 is null then 0 else sr.p1_corner4 * 0.6 end) +
        (case when sr.p2_corner4 is null then 0 else sr.p2_corner4 * 0.3 end) +
        (case when sr.p3_corner4 is null then 0 else sr.p3_corner4 * 0.1 end)
      ) / nullif(
        (case when sr.p1_corner4 is null then 0 else 0.6 end) +
        (case when sr.p2_corner4 is null then 0 else 0.3 end) +
        (case when sr.p3_corner4 is null then 0 else 0.1 end),
        0
      ),
      0
    ),
    1
  ) as pred_wavg3_recent,
  least(
    greatest(
      case
        when sr.p1_corner4 is null or sr.p3_corner4 is null then null
        else sr.p1_corner4 - ((sr.p3_corner4 - sr.p1_corner4)::float / 2.0)
      end,
      0
    ),
    1
  ) as pred_endpoint_trend3,
  least(
    greatest(
      case
        when sr.ols3_points >= 2 and sr.ols3_intercept is not null and sr.ols3_slope is not null
          then sr.ols3_intercept + sr.ols3_slope * 4.0
        else null
      end,
      0
    ),
    1
  ) as pred_ols3_next
from scored_rows sr
