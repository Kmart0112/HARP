{{ config(
  materialized='incremental',
  unique_key=['kettonum', 'held_date', 'distance_m'],
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
    condition_key1::int as distance_m,
    past_starts as same_distance_past_starts,
    past_places as same_distance_past_places,
    past_pos4_agari_synergy as same_distance_past_pos4_agari_synergy,
    past_weighted_starts as same_distance_past_weighted_starts,
    past_weighted_places as same_distance_past_weighted_places,
    past_weighted_pos4_agari_synergy as same_distance_past_weighted_pos4_agari_synergy,
    avg_pos4_agari_synergy as same_distance_avg_pos4_agari_synergy,
    weighted_avg_pos4_agari_synergy as same_distance_weighted_avg_pos4_agari_synergy,
    place_rate as same_distance_place_rate,
    weighted_place_rate as same_distance_weighted_place_rate
  from {{ ref('int_horse_condition_daily_cum_long') }}
  where condition_group = 'distance'
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
