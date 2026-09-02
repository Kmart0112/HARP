{{ config(
  materialized='incremental',
  unique_key=['held_year', 'sex_cd'],
  tags=['feature']
) }}

with incremental_bounds as (
  {{ yearly_incremental_bounds(this, history_years=3) }}
),

base as (
  select
    held_year,
    sex_cd,
    is_place
  from {{ ref('int_race_entry_enriched') }}
  where held_year is not null
    and sex_cd is not null
    and is_place is not null
  {% if is_incremental() %}
    and held_year >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_sex_cd as (
  select
    held_year,
    sex_cd,
    count(*) as starts,
    sum(is_place) as places
  from base
  group by
    held_year,
    sex_cd
),

yearly_sex_cd_roll as (
  select
    ysc.*,
    sum(ysc.starts) over (
      partition by ysc.sex_cd
      order by ysc.held_year
      rows between 3 preceding and 1 preceding
    ) as sex_cd_starts_3y,
    sum(ysc.places) over (
      partition by ysc.sex_cd
      order by ysc.held_year
      rows between 3 preceding and 1 preceding
    ) as sex_cd_places_3y
  from yearly_sex_cd ysc
)

select
  held_year,
  sex_cd,
  sex_cd_starts_3y,
  sex_cd_places_3y,
  case
    when sex_cd_starts_3y is null or sex_cd_starts_3y = 0 then null
    else sex_cd_places_3y::float / nullif(sex_cd_starts_3y, 0)
  end as sex_cd_place_rate_3y
from yearly_sex_cd_roll
{% if is_incremental() %}
where held_year >= (select recalc_from_period from incremental_bounds)
{% endif %}
