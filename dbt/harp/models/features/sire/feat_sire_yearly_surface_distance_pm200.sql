{{ config(
  materialized='incremental',
  unique_key=['sire_id', 'held_year_month', 'surface', 'distance_m'],
  indexes=[{'columns': ['sire_id', 'held_year_month', 'surface', 'distance_m']}],
  tags=['feature','monthly']
) }}

with incremental_bounds as (
  {% if is_incremental() %}
    select
      coalesce(max(held_year_month), '1900-01-01'::timestamp) as max_held_year_month,
      (
        coalesce(max(held_year_month), '1900-01-01'::timestamp)
        - make_interval(months => {{ var('sire_incremental_recalc_months') }})
      )::timestamp as recalc_from_month,
      (
        coalesce(max(held_year_month), '1900-01-01'::timestamp)
        - make_interval(months => {{ var('sire_incremental_recalc_months') }})
        - make_interval(years => {{ var('sire_sample_years') }})
      )::timestamp as hist_from_month
    from {{ this }}
  {% else %}
    select
      null::timestamp as max_held_year_month,
      null::timestamp as recalc_from_month,
      null::timestamp as hist_from_month
  {% endif %}
),

base as (
  select
    sire_id,
    held_year_month,
    surface,
    distance_m,
    is_place,
    is_win,
    pos4_agari_synergy
  from {{ ref('feat_race_entry_base') }}
  where held_year_month is not null
    and sire_id is not null
    and surface is not null
    and distance_m is not null
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_month from incremental_bounds)
  {% endif %}
),

yearly_sire_surface_distance as (
  select
    sire_id,
    held_year_month,
    surface,
    distance_m,
    count(*) as starts,
    sum(is_place) as places,
    sum(is_win) as wins,
    sum(pos4_agari_synergy) as pos4_agari_synergy_sum,
    count(pos4_agari_synergy) as pos4_agari_synergy_count
  from base
  group by
    sire_id,
    held_year_month,
    surface,
    distance_m
),

cur_yearly_sire_surface_distance as (
  select
    *
  from yearly_sire_surface_distance
  {% if is_incremental() %}
    where held_year_month >= (select recalc_from_month from incremental_bounds)
  {% endif %}
),

yearly_sire_surface_distance_pm200_roll as (
  select
    cur.sire_id,
    cur.held_year_month,
    cur.surface,
    cur.distance_m,
    coalesce(sum(hist.starts), 0) as same_surface_dist_pm200_sire_starts_5y,
    coalesce(sum(hist.places), 0) as same_surface_dist_pm200_sire_places_5y,
    coalesce(sum(hist.wins), 0) as same_surface_dist_pm200_sire_wins_5y,
    coalesce(sum(hist.pos4_agari_synergy_sum), 0) as same_surface_dist_pm200_sire_pos4_agari_synergy_sum_5y,
    coalesce(sum(hist.pos4_agari_synergy_count), 0) as same_surface_dist_pm200_sire_pos4_agari_synergy_count_5y
  from cur_yearly_sire_surface_distance cur
  left join yearly_sire_surface_distance hist
    on cur.sire_id = hist.sire_id
    and cur.surface = hist.surface
    and hist.distance_m between cur.distance_m - 200 and cur.distance_m + 200
    and hist.held_year_month < cur.held_year_month
    and hist.held_year_month >= cur.held_year_month - make_interval(years => {{ var('sire_sample_years') }})
  group by
    cur.sire_id,
    cur.held_year_month,
    cur.surface,
    cur.distance_m
)

select
  sire_id,
  held_year_month,
  surface,
  distance_m,
  same_surface_dist_pm200_sire_starts_5y,
  same_surface_dist_pm200_sire_places_5y,
  same_surface_dist_pm200_sire_wins_5y,
  same_surface_dist_pm200_sire_places_5y::float / nullif(same_surface_dist_pm200_sire_starts_5y, 0) as same_surface_dist_pm200_sire_place_rate_5y,
  same_surface_dist_pm200_sire_pos4_agari_synergy_sum_5y::float
    / nullif(same_surface_dist_pm200_sire_pos4_agari_synergy_count_5y, 0)
    as same_surface_dist_pm200_sire_avg_pos4_agari_synergy
from yearly_sire_surface_distance_pm200_roll
