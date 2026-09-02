{{ config(
  materialized='incremental',
  unique_key=['kettonum', 'held_date', 'surface', 'surface_condition_cd'],
  tags=['feature']
) }}

with incremental_bounds as (
  {% if is_incremental() %}
    select
      (
        coalesce(max(held_date), '1900-01-01'::date)
        - ({{ var('incremental_recalc_days') }} * interval '1 day')
      )::date as recalc_from_date
    from {{ this }}
  {% else %}
    select null::date as recalc_from_date
  {% endif %}
),

source as (
  select
    kettonum,
    held_date,
    condition_key1::int as surface,
    condition_key2::int as surface_condition_cd,
    past_starts as same_surface_condition_past_starts,
    past_places as same_surface_condition_past_places,
    past_pos4_agari_synergy as same_surface_condition_past_pos4_agari_synergy,
    past_weighted_starts as same_surface_condition_past_weighted_starts,
    past_weighted_places as same_surface_condition_past_weighted_places,
    past_weighted_pos4_agari_synergy as same_surface_condition_past_weighted_pos4_agari_synergy,
    avg_pos4_agari_synergy as same_surface_condition_avg_pos4_agari_synergy,
    weighted_avg_pos4_agari_synergy as same_surface_condition_weighted_avg_pos4_agari_synergy,
    place_rate as same_surface_condition_place_rate,
    weighted_place_rate as same_surface_condition_weighted_place_rate
  from {{ ref('int_horse_condition_daily_cum_long') }}
  where condition_group = 'surface_condition'
),

filtered as (
  select
    *
  from source
  {% if is_incremental() %}
    where held_date >= (select recalc_from_date from incremental_bounds)
  {% endif %}
)

select *
from filtered
