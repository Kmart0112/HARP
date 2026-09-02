{{ config(
  materialized='incremental',
  unique_key=['jockey_cd', 'held_year_month', 'surface', 'turn_direction'],
  indexes=[{'columns': ['jockey_cd', 'held_year_month', 'surface', 'turn_direction']}],
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
    turn_direction,
    is_place
  from {{ ref('int_race_entry_enriched') }}
  where held_year_month is not null
    and jockey_cd is not null
    and surface is not null
    and turn_direction is not null
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_jockey_surface_turn_direction as (
  select
    jockey_cd,
    held_year_month,
    surface,
    turn_direction,
    count(*) as starts,
    sum(is_place) as places
  from base
  group by
    jockey_cd,
    held_year_month,
    surface,
    turn_direction
),

yearly_jockey_surface_turn_direction_roll as (
  select
    yjstd.*,
    sum(yjstd.starts) over (
      partition by yjstd.jockey_cd, yjstd.surface, yjstd.turn_direction
      order by yjstd.held_year_month
      rows between 35 preceding and 1 preceding
    ) as jockey_surface_turn_direction_starts_3y,
    sum(yjstd.places) over (
      partition by yjstd.jockey_cd, yjstd.surface, yjstd.turn_direction
      order by yjstd.held_year_month
      rows between 35 preceding and 1 preceding
    ) as jockey_surface_turn_direction_places_3y
  from yearly_jockey_surface_turn_direction yjstd
)

select
  jockey_cd,
  held_year_month,
  surface,
  turn_direction,
  jockey_surface_turn_direction_starts_3y,
  jockey_surface_turn_direction_places_3y,
  case
    when jockey_surface_turn_direction_starts_3y is null or jockey_surface_turn_direction_starts_3y = 0 then null
    else jockey_surface_turn_direction_places_3y::float / nullif(jockey_surface_turn_direction_starts_3y, 0)
  end as jockey_surface_turn_direction_place_rate_3y,
  case
    when jockey_surface_turn_direction_starts_3y is null or jockey_surface_turn_direction_starts_3y = 0 then null
    else ((jockey_surface_turn_direction_places_3y + (0.213 * 10))::float / nullif(jockey_surface_turn_direction_starts_3y + 10, 0))
  end as jockey_surface_turn_direction_place_rate_3y_smooth
from yearly_jockey_surface_turn_direction_roll
{% if is_incremental() %}
where held_year_month >= (select recalc_from_period from incremental_bounds)
{% endif %}
