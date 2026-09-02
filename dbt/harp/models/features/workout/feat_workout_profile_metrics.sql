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

long as (
  select
    race_id,
    kettonum,
    held_year_month,
    wood_4f1f_profile_cat3,
    hanro_4f1f_profile_cat3
  from {{ ref('feat_race_entry_base') }}
  {% if is_incremental() %}
    where held_date >= (select recalc_from_date from incremental_bounds)
  {% endif %}
),

wood_profile as (
  select
    *
  from {{ ref('feat_workout_wood_4f1f_profile_cat3_yearly') }}
),

hanro_profile as (
  select
    *
  from {{ ref('feat_workout_hanro_4f1f_profile_cat3_yearly') }}
)

select
  l.race_id,
  l.kettonum,
  wp.wood_4f1f_profile_place_rate_3y_smooth,
  hp.hanro_4f1f_profile_place_rate_3y_smooth
from long l
left join wood_profile wp
  on l.held_year_month = wp.held_year_month
  and l.wood_4f1f_profile_cat3 = wp.wood_4f1f_profile_cat3
left join hanro_profile hp
  on l.held_year_month = hp.held_year_month
  and l.hanro_4f1f_profile_cat3 = hp.hanro_4f1f_profile_cat3
