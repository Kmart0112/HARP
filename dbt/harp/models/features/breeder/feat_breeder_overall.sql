-- 生産者別の年次成績（過去5年移動平均）
{{ config(
  materialized='incremental',
  unique_key=['breeder_cd', 'held_year'],
  indexes=[{'columns': ['breeder_cd', 'held_year']}],
  tags=['feature']
) }}

with incremental_bounds as (
  {{ yearly_incremental_bounds(this, history_years=5) }}
),

base as (
  select
    breeder_cd,
    held_year,
    is_place,
    is_win
  from {{ ref('int_race_entry_enriched') }}
  where held_year is not null
    and breeder_cd is not null
  {% if is_incremental() %}
    and held_year >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_breeder as (
  select
    breeder_cd,
    held_year,
    count(*) as starts,
    sum(is_place) as places,
    sum(is_win) as wins
  from base
  group by
    breeder_cd,
    held_year
),

yearly_breeder_roll as (
  select
    yb.*,
    sum(yb.starts) over (
      partition by yb.breeder_cd
      order by yb.held_year
      rows between 5 preceding and 1 preceding
    ) as breeder_starts_5y,
    sum(yb.places) over (
      partition by yb.breeder_cd
      order by yb.held_year
      rows between 5 preceding and 1 preceding
    ) as breeder_places_5y,
    sum(yb.wins) over (
      partition by yb.breeder_cd
      order by yb.held_year
      rows between 5 preceding and 1 preceding
    ) as breeder_wins_5y
  from yearly_breeder yb
)

select
  breeder_cd,
  held_year,
  breeder_starts_5y,
  breeder_places_5y,
  breeder_wins_5y,
  breeder_places_5y::float / nullif(breeder_starts_5y, 0) as breeder_place_rate_5y,
  ((breeder_places_5y + (0.213 * 30))::float
    / nullif(breeder_starts_5y + 30, 0)) as breeder_place_rate_5y_smooth
from yearly_breeder_roll
{% if is_incremental() %}
where held_year >= (select recalc_from_period from incremental_bounds)
{% endif %}
