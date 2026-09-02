{{ config(materialized='table', tags=['feature','monthly'], enabled=false) }}

with base as (
  select
    jockey_cd,
    held_year_month,
    surface_condition_cd,
    is_place
  from {{ ref('int_race_entry_enriched') }}
  where held_year_month is not null
    and jockey_cd is not null
    and surface_condition_cd is not null
),

yearly_jockey_surface_condition as (
  select
    jockey_cd,
    held_year_month,
    surface_condition_cd,
    count(*) as starts,
    sum(is_place) as places
  from base
  group by
    jockey_cd,
    held_year_month,
    surface_condition_cd
),

yearly_jockey_surface_condition_roll as (
  select
    yjsc.*,
    sum(yjsc.starts) over (
      partition by yjsc.jockey_cd, yjsc.surface_condition_cd
      order by yjsc.held_year_month
      rows between 35 preceding and 1 preceding
    ) as jockey_surface_condition_starts_3y,
    sum(yjsc.places) over (
      partition by yjsc.jockey_cd, yjsc.surface_condition_cd
      order by yjsc.held_year_month
      rows between 35 preceding and 1 preceding
    ) as jockey_surface_condition_places_3y
  from yearly_jockey_surface_condition yjsc
)

select
  jockey_cd,
  held_year_month,
  surface_condition_cd,
  jockey_surface_condition_starts_3y,
  jockey_surface_condition_places_3y,
  case
    when jockey_surface_condition_starts_3y is null or jockey_surface_condition_starts_3y = 0 then null
    else jockey_surface_condition_places_3y::float / nullif(jockey_surface_condition_starts_3y, 0)
  end as jockey_surface_condition_place_rate_3y,
  ((jockey_surface_condition_places_3y + (0.213 * 10))::float / nullif(jockey_surface_condition_starts_3y + 10, 0)) as jockey_surface_condition_place_rate_3y_smooth
from yearly_jockey_surface_condition_roll
