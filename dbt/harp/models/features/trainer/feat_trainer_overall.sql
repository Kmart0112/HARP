-- 厩舎別の年次成績（過去5年移動平均）
{{ config(
  materialized='incremental',
  unique_key=['trainer_cd', 'held_year'],
  tags=['feature']
) }}

with incremental_bounds as (
  {{ yearly_incremental_bounds(this, history_years=5) }}
),

base as (
  select
    trainer_cd,
    held_year,
    is_place
  from {{ ref('int_race_entry_enriched') }}
  where held_year is not null
    and trainer_cd is not null
  {% if is_incremental() %}
    and held_year >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_trainer as (
  select
    trainer_cd,
    held_year,
    count(*) as starts,
    sum(is_place) as places
  from base
  group by
    trainer_cd,
    held_year
),

yearly_trainer_roll as (
  select
    yt.*,
    sum(yt.starts) over (
      partition by yt.trainer_cd
      order by yt.held_year
      rows between 5 preceding and 1 preceding
    ) as trainer_starts_5y,
    sum(yt.places) over (
      partition by yt.trainer_cd
      order by yt.held_year
      rows between 5 preceding and 1 preceding
    ) as trainer_places_5y
  from yearly_trainer yt
),

params as (
  select
    0.22::float as prior_place_rate,
    100::float as prior_strength
)

select
  trainer_cd,
  held_year,
  trainer_starts_5y,
  trainer_places_5y,
  (
    (trainer_places_5y + (params.prior_place_rate * params.prior_strength))
    / nullif(trainer_starts_5y + params.prior_strength, 0)
  ) as trainer_place_rate_5y
from yearly_trainer_roll
cross join params
{% if is_incremental() %}
where held_year >= (select recalc_from_period from incremental_bounds)
{% endif %}
