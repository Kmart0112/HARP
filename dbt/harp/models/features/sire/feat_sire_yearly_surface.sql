{{ config(materialized='table', tags=['feature','monthly'], enabled=false) }}

with base as (
  select
    sire_id,
    held_year_month,
    surface,
    is_place,
    is_win
  from {{ ref('int_race_entry_enriched') }}
  where held_year_month is not null
    and sire_id is not null
    and surface is not null
),

yearly_sire_surface as (
  select
    sire_id,
    held_year_month,
    surface,
    count(*) as starts,
    sum(is_place) as places,
    sum(is_win) as wins
  from base
  group by
    sire_id,
    held_year_month,
    surface
),

yearly_sire_surface_roll as (
  select
    yss.*,
    sum(yss.starts) over (
      partition by yss.sire_id, yss.surface
      order by yss.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_surface_sire_starts_5y,
    sum(yss.places) over (
      partition by yss.sire_id, yss.surface
      order by yss.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_surface_sire_places_5y,
    sum(yss.wins) over (
      partition by yss.sire_id, yss.surface
      order by yss.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_surface_sire_wins_5y
  from yearly_sire_surface yss
)

select
  sire_id,
  held_year_month,
  surface,
  same_surface_sire_starts_5y,
  same_surface_sire_places_5y,
  same_surface_sire_wins_5y,
  same_surface_sire_places_5y::float / nullif(same_surface_sire_starts_5y, 0) as same_surface_sire_place_rate_5y
from yearly_sire_surface_roll
