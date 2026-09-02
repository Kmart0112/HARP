{{ config(
  materialized='incremental',
  unique_key=['jockey_cd', 'held_year_month', 'surface', 'distance_m'],
  indexes=[{'columns': ['jockey_cd', 'held_year_month', 'surface', 'distance_m']}],
  tags=['feature','monthly']
) }}

with incremental_bounds as (
  {{ monthly_incremental_bounds(this, history_years=3) }}
),

base as (
  select
    jockey_cd,
    held_year_month,
    surface,
    distance_m,
    is_place
  from {{ ref('int_race_entry_enriched') }}
  where held_year_month is not null
    and jockey_cd is not null
    and surface is not null
    and distance_m is not null
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_jockey_surface_distance as (
  select
    jockey_cd,
    held_year_month,
    surface,
    distance_m,
    count(*) as starts,
    sum(is_place) as places
  from base
  group by
    jockey_cd,
    held_year_month,
    surface,
    distance_m
),

current_surface_distance as (
  select
    *
  from yearly_jockey_surface_distance
  {% if is_incremental() %}
    where held_year_month >= (select recalc_from_period from incremental_bounds)
  {% endif %}
),

yearly_jockey_surface_distance_exact_roll as (
  select
    cur.jockey_cd,
    cur.held_year_month,
    cur.surface,
    cur.distance_m,
    sum(hist.starts) as jockey_surface_distance_starts_3y,
    sum(hist.places) as jockey_surface_distance_places_3y
  from current_surface_distance cur
  left join yearly_jockey_surface_distance hist
    on cur.jockey_cd = hist.jockey_cd
    and cur.surface = hist.surface
    and cur.distance_m = hist.distance_m
    and hist.held_year_month < cur.held_year_month
    and hist.held_year_month >= cur.held_year_month - make_interval(years => 3)
  group by
    cur.jockey_cd,
    cur.held_year_month,
    cur.surface,
    cur.distance_m
),

yearly_jockey_surface_distance_pm200_roll as (
  select
    cur.jockey_cd,
    cur.held_year_month,
    cur.surface,
    cur.distance_m,
    sum(hist.starts) as jockey_surface_dist_pm200_starts_3y,
    sum(hist.places) as jockey_surface_dist_pm200_places_3y
  from current_surface_distance cur
  left join yearly_jockey_surface_distance hist
    on cur.jockey_cd = hist.jockey_cd
    and cur.surface = hist.surface
    and hist.distance_m between cur.distance_m - 200 and cur.distance_m + 200
    and hist.held_year_month < cur.held_year_month
    and hist.held_year_month >= cur.held_year_month - make_interval(years => 3)
  group by
    cur.jockey_cd,
    cur.held_year_month,
    cur.surface,
    cur.distance_m
)

select
  exact.jockey_cd,
  exact.held_year_month,
  exact.surface,
  exact.distance_m,
  exact.jockey_surface_distance_starts_3y,
  exact.jockey_surface_distance_places_3y,
  case
    when exact.jockey_surface_distance_starts_3y is null or exact.jockey_surface_distance_starts_3y = 0 then null
    else exact.jockey_surface_distance_places_3y::float / nullif(exact.jockey_surface_distance_starts_3y, 0)
  end as jockey_surface_distance_place_rate_3y,
  case
    when exact.jockey_surface_distance_starts_3y is null or exact.jockey_surface_distance_starts_3y = 0 then null
    else ((exact.jockey_surface_distance_places_3y + (0.213 * 10))::float / nullif(exact.jockey_surface_distance_starts_3y + 10, 0))
  end as jockey_surface_distance_place_rate_3y_smooth,
  pm200.jockey_surface_dist_pm200_starts_3y,
  pm200.jockey_surface_dist_pm200_places_3y,
  case
    when pm200.jockey_surface_dist_pm200_starts_3y is null or pm200.jockey_surface_dist_pm200_starts_3y = 0 then null
    else pm200.jockey_surface_dist_pm200_places_3y::float / nullif(pm200.jockey_surface_dist_pm200_starts_3y, 0)
  end as jockey_surface_dist_pm200_place_rate_3y,
  case
    when pm200.jockey_surface_dist_pm200_starts_3y is null or pm200.jockey_surface_dist_pm200_starts_3y = 0 then null
    else ((pm200.jockey_surface_dist_pm200_places_3y + (0.213 * 10))::float / nullif(pm200.jockey_surface_dist_pm200_starts_3y + 10, 0))
  end as jockey_surface_dist_pm200_place_rate_3y_smooth
from yearly_jockey_surface_distance_exact_roll exact
left join yearly_jockey_surface_distance_pm200_roll pm200
  on exact.jockey_cd = pm200.jockey_cd
  and exact.held_year_month = pm200.held_year_month
  and exact.surface = pm200.surface
  and exact.distance_m = pm200.distance_m
