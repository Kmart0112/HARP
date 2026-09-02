-- 厩舎×年齢区分(old_cd)の年次成績（過去5年移動平均）
{{ config(
  materialized='incremental',
  unique_key=['trainer_cd', 'old_cd', 'held_year'],
  indexes=[{'columns': ['trainer_cd', 'old_cd', 'held_year']}],
  tags=['feature']
) }}

with incremental_bounds as (
  {{ yearly_incremental_bounds(this, history_years=5) }}
),

base as (
  select
    trainer_cd,
    old_cd,
    held_year,
    is_place
  from {{ ref('int_race_entry_enriched') }}
  where held_year is not null
    and trainer_cd is not null
    and old_cd is not null
  {% if is_incremental() %}
    and held_year >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_trainer_old as (
  select
    trainer_cd,
    old_cd,
    held_year,
    count(*) as starts,
    sum(is_place) as places
  from base
  group by
    trainer_cd,
    old_cd,
    held_year
),

yearly_trainer_old_roll as (
  select
    yto.*,
    sum(yto.starts) over (
      partition by yto.trainer_cd, yto.old_cd
      order by yto.held_year
      rows between 5 preceding and 1 preceding
    ) as trainer_old_starts_5y,
    sum(yto.places) over (
      partition by yto.trainer_cd, yto.old_cd
      order by yto.held_year
      rows between 5 preceding and 1 preceding
    ) as trainer_old_places_5y
  from yearly_trainer_old yto
)

select
  trainer_cd,
  old_cd,
  held_year,
  trainer_old_starts_5y,
  trainer_old_places_5y,
  trainer_old_places_5y / nullif(trainer_old_starts_5y, 0) as trainer_old_place_rate_5y
from yearly_trainer_old_roll
{% if is_incremental() %}
where held_year >= (select recalc_from_period from incremental_bounds)
{% endif %}
