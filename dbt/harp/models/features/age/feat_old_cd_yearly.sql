{{ config(
  materialized='incremental',
  unique_key=['held_year', 'old_cd'],
  tags=['feature']
) }}

with incremental_bounds as (
  {{ yearly_incremental_bounds(this, history_years=3) }}
),

base as (
  select
    held_year,
    old_cd,
    is_place
  from {{ ref('int_race_entry_enriched') }}
  where held_year is not null
    and old_cd is not null
    and is_place is not null
  {% if is_incremental() %}
    and held_year >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_old_cd as (
  select
    held_year,
    old_cd,
    count(*) as starts,
    sum(is_place) as places
  from base
  group by
    held_year,
    old_cd
),

yearly_old_cd_roll as (
  select
    yoc.*,
    sum(yoc.starts) over (
      partition by yoc.old_cd
      order by yoc.held_year
      rows between 3 preceding and 1 preceding
    ) as old_cd_starts_3y,
    sum(yoc.places) over (
      partition by yoc.old_cd
      order by yoc.held_year
      rows between 3 preceding and 1 preceding
    ) as old_cd_places_3y
  from yearly_old_cd yoc
)

select
  held_year,
  old_cd,
  old_cd_starts_3y,
  old_cd_places_3y,
  case
    when old_cd_starts_3y is null or old_cd_starts_3y = 0 then null
    else old_cd_places_3y::float / nullif(old_cd_starts_3y, 0)
  end as old_cd_place_rate_3y
from yearly_old_cd_roll
{% if is_incremental() %}
where held_year >= (select recalc_from_period from incremental_bounds)
{% endif %}
