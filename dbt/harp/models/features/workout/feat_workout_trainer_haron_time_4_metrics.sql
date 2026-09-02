{{ config(
  materialized='incremental',
  unique_key=['race_id', 'kettonum'],
  tags=['feature'],
  indexes=[
    {'columns': ['race_id', 'kettonum']}
  ]
) }}

with incremental_bounds as (
  {% if is_incremental() %}
    select
      coalesce(max(frh.held_date), '1900-01-01'::date) as max_held_date,
      (
        coalesce(max(frh.held_date), '1900-01-01'::date)
        - ({{ var('incremental_recalc_days') }} * interval '1 day')
      )::date as recalc_from_date
    from {{ this }} t
    left join {{ ref('feat_race_entry_base') }} frh
      on t.race_id = frh.race_id
      and t.kettonum = frh.kettonum
  {% else %}
    select
      null::date as max_held_date,
      null::date as recalc_from_date
  {% endif %}
),

base as (
  select
    race_id,
    kettonum,
    held_year_month,
    trainer_cd,
    wood_haron_time_4,
    hanro_haron_time_4,
    week1_wood_haron_time_4,
    week1_hanro_haron_time_4
  from {{ ref('feat_race_entry_base') }}
  {% if is_incremental() %}
    where held_date >= (select recalc_from_date from incremental_bounds)
  {% endif %}
),

trainer_stats as (
  select
    *
  from {{ ref('feat_workout_trainer_haron_time_4_yearly') }}
)

select
  b.race_id,
  b.kettonum,
  case
    when ts.trainer_wood_haron_time_4_starts_3y is null or ts.trainer_wood_haron_time_4_starts_3y <= 1 then null
    when b.wood_haron_time_4 is null or ts.trainer_wood_haron_time_4_mean_3y is null or ts.trainer_wood_haron_time_4_std_3y is null then null
    else -1.0 * (b.wood_haron_time_4 - ts.trainer_wood_haron_time_4_mean_3y) / greatest(ts.trainer_wood_haron_time_4_std_3y, 0.1)
  end as trainer_wood_haron_time_4_fast_excess_z_3y,
  case
    when ts.trainer_hanro_haron_time_4_starts_3y is null or ts.trainer_hanro_haron_time_4_starts_3y <= 1 then null
    when b.hanro_haron_time_4 is null or ts.trainer_hanro_haron_time_4_mean_3y is null or ts.trainer_hanro_haron_time_4_std_3y is null then null
    else -1.0 * (b.hanro_haron_time_4 - ts.trainer_hanro_haron_time_4_mean_3y) / greatest(ts.trainer_hanro_haron_time_4_std_3y, 0.1)
  end as trainer_hanro_haron_time_4_fast_excess_z_3y,
  case
    when ts.trainer_week1_wood_haron_time_4_starts_3y is null or ts.trainer_week1_wood_haron_time_4_starts_3y <= 1 then null
    when b.week1_wood_haron_time_4 is null or ts.trainer_week1_wood_haron_time_4_mean_3y is null or ts.trainer_week1_wood_haron_time_4_std_3y is null then null
    else -1.0 * (b.week1_wood_haron_time_4 - ts.trainer_week1_wood_haron_time_4_mean_3y) / greatest(ts.trainer_week1_wood_haron_time_4_std_3y, 0.1)
  end as trainer_week1_wood_haron_time_4_fast_excess_z_3y,
  case
    when ts.trainer_week1_hanro_haron_time_4_starts_3y is null or ts.trainer_week1_hanro_haron_time_4_starts_3y <= 1 then null
    when b.week1_hanro_haron_time_4 is null or ts.trainer_week1_hanro_haron_time_4_mean_3y is null or ts.trainer_week1_hanro_haron_time_4_std_3y is null then null
    else -1.0 * (b.week1_hanro_haron_time_4 - ts.trainer_week1_hanro_haron_time_4_mean_3y) / greatest(ts.trainer_week1_hanro_haron_time_4_std_3y, 0.1)
  end as trainer_week1_hanro_haron_time_4_fast_excess_z_3y
from base b
left join trainer_stats ts
  on b.trainer_cd = ts.trainer_cd
  and b.held_year_month = ts.held_year_month
