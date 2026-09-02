{{ config(
  materialized='incremental',
  unique_key=['kettonum', 'held_date'],
  tags=['feature'],
  indexes=[
    {'columns': ['kettonum', 'held_date']}
  ]
) }}

with incremental_bounds as (
  {% if is_incremental() %}
    select
      coalesce(max(held_date), '1900-01-01'::date) as max_held_date,
      (
        coalesce(max(held_date), '1900-01-01'::date)
        - ({{ var('incremental_recalc_days') }} * interval '1 day')
      )::date as recalc_from_date
    from {{ this }}
  {% else %}
    select
      null::date as max_held_date,
      null::date as recalc_from_date
  {% endif %}
),

long as (
  select
    race_id,
    kettonum,
    held_date,
    course_cluster,
    turn_direction,
    has_homestretch_slope,
    jyo_cd,
    distance_m,
    straight_distance_bucket,
    surface,
    surface_condition_cd,
    age
  from {{ ref('feat_race_entry_base') }}
  {% if is_incremental() %}
    where held_date >= (select recalc_from_date from incremental_bounds)
  {% endif %}
),

horse_condition_metrics as (
  select
    *
  from {{ ref('int_horse_condition_daily_cum_long') }}
  {% if is_incremental() %}
    where held_date >= (select recalc_from_date from incremental_bounds)
  {% endif %}
),

condition_metrics_pivot as (
  select
    kettonum,
    held_date,

    max(case when condition_group = 'distance' then past_starts end) as same_distance_past_starts,
    max(case when condition_group = 'distance' then past_places end) as same_distance_past_places,
    max(case when condition_group = 'distance' then past_pos4_agari_synergy end) as same_distance_past_pos4_agari_synergy,
    max(case when condition_group = 'distance' then past_weighted_starts end) as same_distance_past_weighted_starts,
    max(case when condition_group = 'distance' then past_weighted_places end) as same_distance_past_weighted_places,
    max(case when condition_group = 'distance' then past_weighted_pos4_agari_synergy end) as same_distance_past_weighted_pos4_agari_synergy,
    max(case when condition_group = 'distance' then avg_pos4_agari_synergy end) as same_distance_avg_pos4_agari_synergy,
    max(case when condition_group = 'distance' then weighted_avg_pos4_agari_synergy end) as same_distance_weighted_avg_pos4_agari_synergy,
    max(case when condition_group = 'distance' then place_rate end) as same_distance_place_rate,
    max(case when condition_group = 'distance' then weighted_place_rate end) as same_distance_weighted_place_rate,

    max(case when condition_group = 'surface_condition' then past_starts end) as same_surface_condition_past_starts,
    max(case when condition_group = 'surface_condition' then past_places end) as same_surface_condition_past_places,
    max(case when condition_group = 'surface_condition' then past_pos4_agari_synergy end) as same_surface_condition_past_pos4_agari_synergy,
    max(case when condition_group = 'surface_condition' then past_weighted_starts end) as same_surface_condition_past_weighted_starts,
    max(case when condition_group = 'surface_condition' then past_weighted_places end) as same_surface_condition_past_weighted_places,
    max(case when condition_group = 'surface_condition' then past_weighted_pos4_agari_synergy end) as same_surface_condition_past_weighted_pos4_agari_synergy,
    max(case when condition_group = 'surface_condition' then avg_pos4_agari_synergy end) as same_surface_condition_avg_pos4_agari_synergy,
    max(case when condition_group = 'surface_condition' then weighted_avg_pos4_agari_synergy end) as same_surface_condition_weighted_avg_pos4_agari_synergy,
    max(case when condition_group = 'surface_condition' then place_rate end) as same_surface_condition_place_rate,
    max(case when condition_group = 'surface_condition' then weighted_place_rate end) as same_surface_condition_weighted_place_rate,

    max(case when condition_group = 'turn_direction' then past_starts end) as same_turn_direction_past_starts,
    max(case when condition_group = 'turn_direction' then past_places end) as same_turn_direction_past_places,
    max(case when condition_group = 'turn_direction' then past_pos4_agari_synergy end) as same_turn_direction_past_pos4_agari_synergy,
    max(case when condition_group = 'turn_direction' then past_weighted_starts end) as same_turn_direction_past_weighted_starts,
    max(case when condition_group = 'turn_direction' then past_weighted_places end) as same_turn_direction_past_weighted_places,
    max(case when condition_group = 'turn_direction' then past_weighted_pos4_agari_synergy end) as same_turn_direction_past_weighted_pos4_agari_synergy,
    max(case when condition_group = 'turn_direction' then avg_pos4_agari_synergy end) as same_turn_direction_avg_pos4_agari_synergy,
    max(case when condition_group = 'turn_direction' then weighted_avg_pos4_agari_synergy end) as same_turn_direction_weighted_avg_pos4_agari_synergy,
    max(case when condition_group = 'turn_direction' then place_rate end) as same_turn_direction_place_rate,
    max(case when condition_group = 'turn_direction' then weighted_place_rate end) as same_turn_direction_weighted_place_rate,

    max(case when condition_group = 'turn_direction_surface' then past_starts end) as same_turn_direction_surface_past_starts,
    max(case when condition_group = 'turn_direction_surface' then past_places end) as same_turn_direction_surface_past_places,
    max(case when condition_group = 'turn_direction_surface' then past_pos4_agari_synergy end) as same_turn_direction_surface_past_pos4_agari_synergy,
    max(case when condition_group = 'turn_direction_surface' then past_weighted_starts end) as same_turn_direction_surface_past_weighted_starts,
    max(case when condition_group = 'turn_direction_surface' then past_weighted_places end) as same_turn_direction_surface_past_weighted_places,
    max(case when condition_group = 'turn_direction_surface' then past_weighted_pos4_agari_synergy end) as same_turn_direction_surface_past_weighted_pos4_agari_synergy,
    max(case when condition_group = 'turn_direction_surface' then avg_pos4_agari_synergy end) as same_turn_direction_surface_avg_pos4_agari_synergy,
    max(case when condition_group = 'turn_direction_surface' then weighted_avg_pos4_agari_synergy end) as same_turn_direction_surface_weighted_avg_pos4_agari_synergy,
    max(case when condition_group = 'turn_direction_surface' then place_rate end) as same_turn_direction_surface_place_rate,
    max(case when condition_group = 'turn_direction_surface' then weighted_place_rate end) as same_turn_direction_surface_weighted_place_rate,

    max(case when condition_group = 'homestretch_slope_surface' then past_starts end) as same_homestretch_slope_surface_past_starts,
    max(case when condition_group = 'homestretch_slope_surface' then past_places end) as same_homestretch_slope_surface_past_places,
    max(case when condition_group = 'homestretch_slope_surface' then past_pos4_agari_synergy end) as same_homestretch_slope_surface_past_pos4_agari_synergy,
    max(case when condition_group = 'homestretch_slope_surface' then past_weighted_starts end) as same_homestretch_slope_surface_past_weighted_starts,
    max(case when condition_group = 'homestretch_slope_surface' then past_weighted_places end) as same_homestretch_slope_surface_past_weighted_places,
    max(case when condition_group = 'homestretch_slope_surface' then past_weighted_pos4_agari_synergy end) as same_homestretch_slope_surface_past_weighted_pos4_agari_synergy,
    max(case when condition_group = 'homestretch_slope_surface' then avg_pos4_agari_synergy end) as same_homestretch_slope_surface_avg_pos4_agari_synergy,
    max(case when condition_group = 'homestretch_slope_surface' then weighted_avg_pos4_agari_synergy end) as same_homestretch_slope_surface_weighted_avg_pos4_agari_synergy,
    max(case when condition_group = 'homestretch_slope_surface' then place_rate end) as same_homestretch_slope_surface_place_rate,
    max(case when condition_group = 'homestretch_slope_surface' then weighted_place_rate end) as same_homestretch_slope_surface_weighted_place_rate,

    max(case when condition_group = 'straight_distance_bucket_surface' then past_starts end) as same_straight_distance_bucket_surface_past_starts,
    max(case when condition_group = 'straight_distance_bucket_surface' then past_places end) as same_straight_distance_bucket_surface_past_places,
    max(case when condition_group = 'straight_distance_bucket_surface' then past_pos4_agari_synergy end) as same_straight_distance_bucket_surface_past_pos4_agari_synergy,
    max(case when condition_group = 'straight_distance_bucket_surface' then past_weighted_starts end) as same_straight_distance_bucket_surface_past_weighted_starts,
    max(case when condition_group = 'straight_distance_bucket_surface' then past_weighted_places end) as same_straight_distance_bucket_surface_past_weighted_places,
    max(case when condition_group = 'straight_distance_bucket_surface' then past_weighted_pos4_agari_synergy end) as same_straight_distance_bucket_surface_past_weighted_pos4_agari_synergy,
    max(case when condition_group = 'straight_distance_bucket_surface' then avg_pos4_agari_synergy end) as same_straight_distance_bucket_surface_avg_pos4_agari_synergy,
    max(case when condition_group = 'straight_distance_bucket_surface' then weighted_avg_pos4_agari_synergy end) as same_straight_distance_bucket_surface_weighted_avg_pos4_agari_synergy,
    max(case when condition_group = 'straight_distance_bucket_surface' then place_rate end) as same_straight_distance_bucket_surface_place_rate,
    max(case when condition_group = 'straight_distance_bucket_surface' then weighted_place_rate end) as same_straight_distance_bucket_surface_weighted_place_rate,

    max(case when condition_group = 'jyo_distance' then past_starts end) as same_jyo_distance_past_starts,
    max(case when condition_group = 'jyo_distance' then past_places end) as same_jyo_distance_past_places,
    max(case when condition_group = 'jyo_distance' then past_pos4_agari_synergy end) as same_jyo_distance_past_pos4_agari_synergy,
    max(case when condition_group = 'jyo_distance' then past_weighted_starts end) as same_jyo_distance_past_weighted_starts,
    max(case when condition_group = 'jyo_distance' then past_weighted_places end) as same_jyo_distance_past_weighted_places,
    max(case when condition_group = 'jyo_distance' then past_weighted_pos4_agari_synergy end) as same_jyo_distance_past_weighted_pos4_agari_synergy,
    max(case when condition_group = 'jyo_distance' then avg_pos4_agari_synergy end) as same_jyo_distance_avg_pos4_agari_synergy,
    max(case when condition_group = 'jyo_distance' then weighted_avg_pos4_agari_synergy end) as same_jyo_distance_weighted_avg_pos4_agari_synergy,
    max(case when condition_group = 'jyo_distance' then place_rate end) as same_jyo_distance_place_rate,
    max(case when condition_group = 'jyo_distance' then weighted_place_rate end) as same_jyo_distance_weighted_place_rate
  from horse_condition_metrics
  group by
    kettonum,
    held_date
),

hourse_past_cluster as (
  select
    *
  from {{ ref('int_horse_same_cluster_daily_cum') }}
),
hourse_past_pace_ntile as (
  select
    *
  from {{ ref('feat_horse_pace_ntile') }}
),
horse_past_overall as (
  select
    *
  from {{ ref('feat_horse_overall') }}
)

select
    l.kettonum,
    l.held_date,

    same_cluster_past_starts,
    case
      when same_cluster_past_starts = 0 then 1
      else 0
    end as same_cluster_first_start_flag,
    same_cluster_past_places,
    same_cluster_past_time_diffs,
    same_cluster_past_pos4_agari_synergy,
    same_cluster_past_weighted_starts,
    same_cluster_past_weighted_places,
    same_cluster_past_weighted_time_diffs,
    same_cluster_past_weighted_pos4_agari_synergy,
    same_cluster_avg_time_diffs,
    same_cluster_avg_pos4_agari_synergy,
    same_cluster_place_rate,

    same_distance_past_starts,
    same_distance_past_places,
    same_distance_past_pos4_agari_synergy,
    same_distance_past_weighted_starts,
    same_distance_past_weighted_places,
    same_distance_past_weighted_pos4_agari_synergy,
    same_distance_avg_pos4_agari_synergy,
    same_distance_weighted_avg_pos4_agari_synergy,
    same_distance_place_rate,
    same_distance_weighted_place_rate,

    same_surface_condition_past_starts,
    same_surface_condition_past_places,
    same_surface_condition_past_pos4_agari_synergy,
    same_surface_condition_past_weighted_starts,
    same_surface_condition_past_weighted_places,
    same_surface_condition_past_weighted_pos4_agari_synergy,
    same_surface_condition_avg_pos4_agari_synergy,
    same_surface_condition_weighted_avg_pos4_agari_synergy,
    same_surface_condition_place_rate,
    same_surface_condition_weighted_place_rate,

    same_turn_direction_past_starts,
    same_turn_direction_past_places,
    same_turn_direction_past_pos4_agari_synergy,
    same_turn_direction_past_weighted_starts,
    same_turn_direction_past_weighted_places,
    same_turn_direction_past_weighted_pos4_agari_synergy,
    same_turn_direction_avg_pos4_agari_synergy,
    same_turn_direction_weighted_avg_pos4_agari_synergy,
    same_turn_direction_place_rate,
    same_turn_direction_weighted_place_rate,

    same_turn_direction_surface_past_starts,
    same_turn_direction_surface_past_places,
    same_turn_direction_surface_past_pos4_agari_synergy,
    same_turn_direction_surface_past_weighted_starts,
    same_turn_direction_surface_past_weighted_places,
    same_turn_direction_surface_past_weighted_pos4_agari_synergy,
    same_turn_direction_surface_avg_pos4_agari_synergy,
    same_turn_direction_surface_weighted_avg_pos4_agari_synergy,
    same_turn_direction_surface_place_rate,
    same_turn_direction_surface_weighted_place_rate,

    same_homestretch_slope_surface_past_starts,
    same_homestretch_slope_surface_past_places,
    same_homestretch_slope_surface_past_pos4_agari_synergy,
    same_homestretch_slope_surface_past_weighted_starts,
    same_homestretch_slope_surface_past_weighted_places,
    same_homestretch_slope_surface_past_weighted_pos4_agari_synergy,
    same_homestretch_slope_surface_avg_pos4_agari_synergy,
    same_homestretch_slope_surface_weighted_avg_pos4_agari_synergy,
    same_homestretch_slope_surface_place_rate,
    same_homestretch_slope_surface_weighted_place_rate,

    same_straight_distance_bucket_surface_past_starts,
    same_straight_distance_bucket_surface_past_places,
    same_straight_distance_bucket_surface_past_pos4_agari_synergy,
    same_straight_distance_bucket_surface_past_weighted_starts,
    same_straight_distance_bucket_surface_past_weighted_places,
    same_straight_distance_bucket_surface_past_weighted_pos4_agari_synergy,
    same_straight_distance_bucket_surface_avg_pos4_agari_synergy,
    same_straight_distance_bucket_surface_weighted_avg_pos4_agari_synergy,
    same_straight_distance_bucket_surface_place_rate,
    same_straight_distance_bucket_surface_weighted_place_rate,

    same_jyo_distance_past_starts,
    same_jyo_distance_past_places,
    same_jyo_distance_past_pos4_agari_synergy,
    same_jyo_distance_past_weighted_starts,
    same_jyo_distance_past_weighted_places,
    same_jyo_distance_past_weighted_pos4_agari_synergy,
    same_jyo_distance_avg_pos4_agari_synergy,
    same_jyo_distance_weighted_avg_pos4_agari_synergy,
    same_jyo_distance_place_rate,
    same_jyo_distance_weighted_place_rate,

    pace_ntile1_past_starts,
    pace_ntile1_past_places,
    pace_ntile1_past_pos4_agari_synergy,
    pace_ntile1_past_weighted_starts,
    pace_ntile1_past_weighted_places,
    pace_ntile1_past_weighted_pos4_agari_synergy,
    pace_ntile1_avg_pos4_agari_synergy,
    pace_ntile1_weighted_avg_pos4_agari_synergy,
    pace_ntile1_place_rate,
    pace_ntile1_weighted_place_rate,

    pace_ntile2_past_starts,
    pace_ntile2_past_places,
    pace_ntile2_past_pos4_agari_synergy,
    pace_ntile2_past_weighted_starts,
    pace_ntile2_past_weighted_places,
    pace_ntile2_past_weighted_pos4_agari_synergy,
    pace_ntile2_avg_pos4_agari_synergy,
    pace_ntile2_weighted_avg_pos4_agari_synergy,
    pace_ntile2_place_rate,
    pace_ntile2_weighted_place_rate,

    pace_ntile3_past_starts,
    pace_ntile3_past_places,
    pace_ntile3_past_pos4_agari_synergy,
    pace_ntile3_past_weighted_starts,
    pace_ntile3_past_weighted_places,
    pace_ntile3_past_weighted_pos4_agari_synergy,
    pace_ntile3_avg_pos4_agari_synergy,
    pace_ntile3_weighted_avg_pos4_agari_synergy,
    pace_ntile3_place_rate,
    pace_ntile3_weighted_place_rate,

    pace_fast_minus_slow_place_rate,
    pace_fast_minus_slow_weighted_place_rate,

    past_starts,
    past_places,
    past_weighted_starts,
    past_weighted_places,
    past_weighted_place_rate

from long l
left join hourse_past_cluster c
  using (kettonum, held_date, course_cluster)
left join condition_metrics_pivot cmp
  using (kettonum, held_date)
left join hourse_past_pace_ntile pnt
  using (kettonum, held_date)
left join horse_past_overall o
  using (kettonum, held_date)
