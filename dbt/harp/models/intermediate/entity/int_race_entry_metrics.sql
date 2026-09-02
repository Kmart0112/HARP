{{ config(
  materialized='table',
  tags=['feature'],
  indexes=[
    {'columns': ['race_id', 'kettonum']}
  ]
) }}

with base as (
  select
    race_id,
    kettonum,
    held_year,
    held_year_month,
    jyo_cd,
    distance_m,
    surface,
    turn_direction,
    straight_distance_m,
    track_cd,
    surface_condition_cd,
    jockey_cd,
    course_cluster,
    time_sec,
    agari3f,
    ten3f,
    ten4f,
    running_style_cd,
    time_diff,
    corner4_pos,
    pace_type,
    pos4_good,
    agari_good
  from {{ ref('int_race_entry_enriched') }}
),

course_time as (
  select
    *
  from {{ ref('feat_course_time_baseline') }}
),

jockey_yearly_overall as (
  select
    *
  from {{ ref('feat_jockey_yearly_overall') }}
),

jockey_yearly_cluster as (
  select
    *
  from {{ ref('feat_jockey_yearly_cluster') }}
),

jockey_yearly_surface_jyo as (
  select
    *
  from {{ ref('feat_jockey_yearly_surface_jyo') }}
),

jockey_yearly_surface_distance as (
  select
    *
  from {{ ref('feat_jockey_yearly_surface_distance') }}
),

jockey_yearly_surface_straight_distance_bucket as (
  select
    *
  from {{ ref('feat_jockey_yearly_surface_straight_distance_bucket') }}
),

jockey_yearly_surface_turn_direction as (
  select
    *
  from {{ ref('feat_jockey_yearly_surface_turn_direction') }}
),

jockey_yearly_turn_direction as (
  select
    *
  from {{ ref('feat_jockey_yearly_turn_direction') }}
),

race_stats as (
  select
    f.race_id,
    avg(f.pos4_good) as avg_pos4_good_race,
    stddev_samp(f.pos4_good) as std_pos4_good_race,
    avg(f.agari_good) as avg_agari_good_race,
    stddev_samp(f.agari_good) as std_agari_good_race
  from base f
  group by f.race_id
)

select
  f.race_id,
  f.kettonum,
  f.time_sec - b.avg_time_sec_5y as time_vs_avg,
  (f.time_sec - b.avg_time_sec_5y) / nullif(b.std_time_sec_5y, 0) as time_vs_pace_avg,
  (f.agari3f - b.avg_agari3f_5y) / nullif(b.std_agari3f_5y, 0) as relative_agari3f,
  f.ten3f - b.avg_ten3f_5y as ten3f_vs_avg,
  (f.ten3f - b.avg_ten3f_5y) / nullif(b.std_ten3f_5y, 0) as ten3f_vs_avg_z,
  (b.avg_ten3f_5y - f.ten3f) / nullif(b.std_ten3f_5y, 0) as ten3f_avg_z,
  f.ten4f - b.avg_ten4f_5y as ten4f_vs_avg,
  case
    when f.running_style_cd = 1 then f.ten4f - b.avg_ten4f_5y
    else null
  end as ten4f_vs_avg_front_runners,
  -(case when f.time_diff > 0 then f.time_diff else 0 end)
    - f.pace_type * (0.5 - f.corner4_pos) as time_diff_adjusted,
  0.6 * ((f.pos4_good - rs.avg_pos4_good_race) / nullif(rs.std_pos4_good_race, 0))
    + ((f.agari_good - rs.avg_agari_good_race) / nullif(rs.std_agari_good_race, 0))
    as pos4_agari_synergy,
  (f.pos4_good - rs.avg_pos4_good_race) / nullif(rs.std_pos4_good_race, 0) as pos4_z,
  (b.avg_ten3f_5y - f.ten3f) / nullif(b.std_ten3f_5y, 0)
    + (f.pos4_good - rs.avg_pos4_good_race) / nullif(rs.std_pos4_good_race, 0)
    as pace_front_disadvantage,
  ((f.pos4_good - rs.avg_pos4_good_race) / nullif(rs.std_pos4_good_race, 0) * 10 + 50)
    * ((f.agari_good - rs.avg_agari_good_race) / nullif(rs.std_agari_good_race, 0) * 10 + 50)
    / 100 as pos4_agari_synergy_hensachi,
  dj.jockey_starts_3y,
  dj.jockey_places_3y,
  dj.jockey_place_rate_3y as jockey_avg_place_rate,
  dj.jockey_place_rate_3y_smooth as jockey_avg_place_rate_smooth,
  dj.jockey_place_rate_3y_logit,
  dj.jockey_place_rate_3y_logit_smooth,
  dj.jockey_place_rate_3y_smooth,
  dj.jockey_place_rate_3y as jockey_avg_place_rate_corrected,
  dj.jockey_place_rate_3y_smooth as jockey_avg_place_rate_corrected_smooth,
  djc.jockey_cluster_place_rate_3y as jockey_cluster_avg_place_rate_corrected,
  djc.jockey_cluster_place_rate_3y_smooth as jockey_cluster_avg_place_rate_corrected_smooth,
  djc.jockey_cluster_avg_diff_logit_smooth,
  djsd.jockey_surface_dist_pm200_place_rate_3y_smooth,
  djssdb.jockey_surface_straight_distance_bucket_place_rate_3y_smooth,
  djstd.jockey_surface_turn_direction_place_rate_3y_smooth,
  djtd.jockey_turn_direction_place_rate_3y_smooth,
  djsj.jockey_surface_jyo_place_rate_3y_smooth,
  case
    when djsj.jockey_surface_jyo_place_rate_3y_smooth is null or dj.jockey_place_rate_3y_smooth is null then null
    else
      ln(
        least(greatest(djsj.jockey_surface_jyo_place_rate_3y_smooth, 1e-6), 1 - 1e-6)
        / (1 - least(greatest(djsj.jockey_surface_jyo_place_rate_3y_smooth, 1e-6), 1 - 1e-6))
      )
      -
      ln(
        least(greatest(dj.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6)
        / (1 - least(greatest(dj.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6))
      )
  end as jockey_surface_jyo_avg_diff_logit_smooth,
  case
    when djssdb.jockey_surface_straight_distance_bucket_place_rate_3y_smooth is null
      or dj.jockey_place_rate_3y_smooth is null then null
    else
      ln(
        least(greatest(djssdb.jockey_surface_straight_distance_bucket_place_rate_3y_smooth, 1e-6), 1 - 1e-6)
        / (1 - least(greatest(djssdb.jockey_surface_straight_distance_bucket_place_rate_3y_smooth, 1e-6), 1 - 1e-6))
      )
      -
      ln(
        least(greatest(dj.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6)
        / (1 - least(greatest(dj.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6))
      )
  end as jockey_surface_straight_distance_bucket_avg_diff_logit_smooth,
  case
    when djstd.jockey_surface_turn_direction_place_rate_3y_smooth is null
      or dj.jockey_place_rate_3y_smooth is null then null
    else
      ln(
        least(greatest(djstd.jockey_surface_turn_direction_place_rate_3y_smooth, 1e-6), 1 - 1e-6)
        / (1 - least(greatest(djstd.jockey_surface_turn_direction_place_rate_3y_smooth, 1e-6), 1 - 1e-6))
      )
      -
      ln(
        least(greatest(dj.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6)
        / (1 - least(greatest(dj.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6))
      )
  end as jockey_surface_turn_direction_avg_diff_logit_smooth,
  case
    when djtd.jockey_turn_direction_place_rate_3y_smooth is null
      or dj.jockey_place_rate_3y_smooth is null then null
    else
      ln(
        least(greatest(djtd.jockey_turn_direction_place_rate_3y_smooth, 1e-6), 1 - 1e-6)
        / (1 - least(greatest(djtd.jockey_turn_direction_place_rate_3y_smooth, 1e-6), 1 - 1e-6))
      )
      -
      ln(
        least(greatest(dj.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6)
        / (1 - least(greatest(dj.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6))
      )
  end as jockey_turn_direction_avg_diff_logit_smooth

from base f
left join course_time b
  on f.held_year = b.held_year
  and f.jyo_cd = b.jyo_cd
  and f.distance_m = b.distance_m
  and f.surface = b.surface
  and f.track_cd = b.track_cd
  and f.surface_condition_cd = b.surface_condition_cd
left join jockey_yearly_overall dj
  on f.jockey_cd = dj.jockey_cd
  and f.held_year_month = dj.held_year_month
left join jockey_yearly_cluster djc
  on f.jockey_cd = djc.jockey_cd
  and f.course_cluster = djc.course_cluster
  and f.held_year_month = djc.held_year_month
left join jockey_yearly_surface_distance djsd
  on f.jockey_cd = djsd.jockey_cd
  and f.held_year_month = djsd.held_year_month
  and f.surface = djsd.surface
  and f.distance_m = djsd.distance_m
left join jockey_yearly_surface_straight_distance_bucket djssdb
  on f.jockey_cd = djssdb.jockey_cd
  and f.held_year_month = djssdb.held_year_month
  and f.surface = djssdb.surface
  and (
    case
      when f.straight_distance_m is null then null
      when f.straight_distance_m < 300 then 1
      when f.straight_distance_m < 350 then 2
      when f.straight_distance_m < 400 then 3
      when f.straight_distance_m < 500 then 4
      else 5
    end
  ) = djssdb.straight_distance_bucket
left join jockey_yearly_surface_turn_direction djstd
  on f.jockey_cd = djstd.jockey_cd
  and f.held_year_month = djstd.held_year_month
  and f.surface = djstd.surface
  and f.turn_direction = djstd.turn_direction
left join jockey_yearly_turn_direction djtd
  on f.jockey_cd = djtd.jockey_cd
  and f.held_year_month = djtd.held_year_month
  and f.turn_direction = djtd.turn_direction
left join jockey_yearly_surface_jyo djsj
  on f.jockey_cd = djsj.jockey_cd
  and f.held_year_month = djsj.held_year_month
  and f.surface = djsj.surface
  and f.jyo_cd = djsj.jyo_cd
left join race_stats rs
  on f.race_id = rs.race_id
