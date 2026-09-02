{{ config(
  materialized='incremental',
  unique_key=['held_year', 'age'],
  tags=['feature']
) }}

with incremental_bounds as (
  {{ yearly_incremental_bounds(this, history_years=3) }}
),

base as (
  select
    held_year,
    case
      when age >= 8 then 8
      else age
    end as age,
    is_place
  from {{ ref('int_race_entry_enriched') }}
  where held_year is not null
    and age is not null
    and is_place is not null
  {% if is_incremental() %}
    and held_year >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_age as (
  select
    held_year,
    age,
    count(*) as starts,
    sum(is_place) as places
  from base
  group by
    held_year,
    age
),

yearly_age_roll as (
  select
    ya.*,
    sum(ya.starts) over (
      partition by ya.age
      order by ya.held_year
      rows between 3 preceding and 1 preceding
    ) as age_starts_3y,
    sum(ya.places) over (
      partition by ya.age
      order by ya.held_year
      rows between 3 preceding and 1 preceding
    ) as age_places_3y
  from yearly_age ya
)

select
  held_year,
  age,
  age_starts_3y,
  age_places_3y,
  case
    when age_starts_3y is null or age_starts_3y = 0 then null
    else age_places_3y::float / nullif(age_starts_3y, 0)
  end as age_place_rate_3y
from yearly_age_roll
{% if is_incremental() %}
where held_year >= (select recalc_from_period from incremental_bounds)
{% endif %}
