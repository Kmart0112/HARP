{{ config(
  materialized='incremental',
  unique_key=['trainer_cd', 'surface', 'held_year'],
  tags=['feature']
) }}

with incremental_bounds as (
  {{ yearly_incremental_bounds(this, history_years=5) }}
),

base as (
  select
    trainer_cd,
    surface,
    held_year,
    is_place
  from {{ ref('int_race_entry_enriched') }}
  where held_year is not null
    and trainer_cd is not null
    and surface is not null
  {% if is_incremental() %}
    and held_year >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_trainer_surface as (
  select
    trainer_cd,
    surface,
    held_year,
    count(*) as starts,
    sum(is_place) as places
  from base
  group by
    trainer_cd,
    surface,
    held_year
),

yearly_trainer_surface_roll as (
  select
    yts.*,
    sum(yts.starts) over (
      partition by yts.trainer_cd, yts.surface
      order by yts.held_year
      rows between 5 preceding and 1 preceding
    ) as trainer_surface_starts_5y,
    sum(yts.places) over (
      partition by yts.trainer_cd, yts.surface
      order by yts.held_year
      rows between 5 preceding and 1 preceding
    ) as trainer_surface_places_5y
  from yearly_trainer_surface yts
),

params as (
  select
    0.22::float as prior_place_rate,
    60::float as prior_strength
)

select
  trainer_cd,
  surface,
  held_year,
  trainer_surface_starts_5y,
  trainer_surface_places_5y,
  trainer_surface_places_5y::float / nullif(trainer_surface_starts_5y, 0) as trainer_surface_place_rate_5y,
  (
    (trainer_surface_places_5y + (params.prior_place_rate * params.prior_strength))
    / nullif(trainer_surface_starts_5y + params.prior_strength, 0)
  ) as trainer_surface_place_rate_5y_smooth
from yearly_trainer_surface_roll
cross join params
{% if is_incremental() %}
where held_year >= (select recalc_from_period from incremental_bounds)
{% endif %}
