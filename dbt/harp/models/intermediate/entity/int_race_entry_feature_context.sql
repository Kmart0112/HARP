{{ config(
  materialized='incremental',
  unique_key=['race_id', 'kettonum'],
  on_schema_change='sync_all_columns',
  tags=['feature_matrix', 'training'],
  indexes=[
    {'columns': ['race_id', 'kettonum'], 'unique': True},
    {'columns': ['held_date']}
  ]
) }}

with spine as (
  select *
  from {{ ref('int_race_entry_spine') }}
  {% if var('target_held_date', none) is not none %}
    where held_date = '{{ var("target_held_date") }}'::date
  {% elif var('race_from_date', none) is not none or var('race_to_date', none) is not none %}
    where 1 = 1
    {% if var('race_from_date', none) is not none %}
      and held_date >= '{{ var("race_from_date") }}'::date
    {% endif %}
    {% if var('race_to_date', none) is not none %}
      and held_date <= '{{ var("race_to_date") }}'::date
    {% endif %}
  {% elif is_incremental() %}
    where held_date >= current_date - interval '7 days'
  {% endif %}
),

declared as (
  select *
  from {{ ref('fct_race_entry_declared') }}
),

races as (
  select *
  from {{ ref('fct_race_basic') }}
),

resolved as (
  select
    d.race_id,
    d.kettonum,
    d.held_date,
    r.held_year,
    r.held_year_month,
    d.datakubun,
    d.horse_name,
    d.age,
    d.h_weight,
    d.weight_change,
    d.sex_cd,
    d.kinryo,
    d.tozai_cd,
    d.horse_number,
    d.gate_number,
    d.jockey_cd,
    d.jockey_cat,
    d.trainer_cd,
    d.blinker_cd,
    d.ijyo_cd,
    d.is_scratched_or_excluded as is_scratched,
    s.entry_status,
    s.is_prediction_target,
    d.sire_cat,
    d.breeder_cat,
    d.breeder_cd,
    d.trainer_cat,
    d.sire_id,
    d.sire_name,
    d.dam_id,
    d.damsire_id,
    d.birth_date,
    r.round,
    r.race_name,
    r.jyo_cd,
    r.distance_m,
    r.surface,
    r.base_surface_condition_cd as surface_condition_cd,
    r.base_weather_cd as weather_cd,
    r.base_jyuryo_cd as jyuryo_cd,
    r.course_kubun_cd,
    r.old_cd,
    r.race_level,
    r.grade_cd,
    r.track_cd,
    r.hassotime,
    r.planned_num_starters as num_starters,
    r.planned_num_starters,
    r.course_cluster,
    r.turn_direction,
    r.turn_direction_cd,
    r.course_variant,
    r.straight_distance_m,
    r.elevation_diff_m,
    r.has_slope,
    r.has_homestretch_slope,
    r.has_uphill_finish
  from spine s
  inner join declared d
    on s.race_id = d.race_id
   and s.kettonum = d.kettonum
  left join races r
    on s.race_id = r.race_id
)

select
  *,
  case
    when h_weight is null then null
    when h_weight <= 400 then 0
    when h_weight >= 526 then 6
    when h_weight between 401 and 425 then 1
    when h_weight between 426 and 450 then 2
    when h_weight between 451 and 475 then 3
    when h_weight between 476 and 500 then 4
    when h_weight between 501 and 525 then 5
    else null
  end as h_weight_bin,
  horse_number / nullif(num_starters, 0)::float as horse_number_ratio,
  case
    when straight_distance_m is null then null
    when straight_distance_m < 300 then 1
    when straight_distance_m < 350 then 2
    when straight_distance_m < 400 then 3
    when straight_distance_m < 500 then 4
    else 5
  end as straight_distance_bucket,
  extract(month from held_date)::int as held_month,
  age * 12 + extract(month from held_date)::int as age_month,
  case
    when old_cd in (1, 2) then held_date - birth_date
    else null
  end as age_days,
  case
    when kinryo is null then null
    when sex_cd = 2 and old_cd = 0 then kinryo + 2
    else kinryo
  end as kinryo_adj,
  case
    when tozai_cd = 1 and jyo_cd in (3, 5, 6) then 0
    when tozai_cd = 1 and jyo_cd not in (8, 9, 10) then 1
    when tozai_cd = 2 and jyo_cd in (8, 9, 10) then 0
    when tozai_cd = 2 and jyo_cd not in (3, 5, 6) then 1
    else 2
  end as ensei_type,
  now() as updated_at
from resolved
