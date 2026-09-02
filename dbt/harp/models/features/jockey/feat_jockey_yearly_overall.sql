-- ジョッキー別の年月次成績（過去3年移動平均）
{{ config(
  materialized='incremental',
  unique_key=['jockey_cd', 'held_year_month'],
  indexes=[{'columns': ['jockey_cd', 'held_year_month']}],
  tags=['feature','monthly']
) }}

with incremental_bounds as (
  {{ monthly_incremental_bounds(this, history_years=3) }}
),

base as (
  select
    jockey_cd,
    held_year_month,
    is_place,
    is_win
  from {{ ref('int_race_entry_enriched') }}
  where held_year_month is not null
    and jockey_cd is not null
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_jockey as (
  select
    jockey_cd,
    held_year_month,
    count(*) as starts,
    sum(is_place) as places,
    sum(is_win) as wins
  from base
  group by
    jockey_cd,
    held_year_month
),

yearly_jockey_roll as (
  select
    yj.*,
    sum(yj.starts) over (
      partition by yj.jockey_cd
      order by yj.held_year_month
      rows between 35 preceding and 1 preceding
    ) as jockey_starts_3y,
    sum(yj.places) over (
      partition by yj.jockey_cd
      order by yj.held_year_month
      rows between 35 preceding and 1 preceding
    ) as jockey_places_3y,
    sum(yj.wins) over (
      partition by yj.jockey_cd
      order by yj.held_year_month
      rows between 35 preceding and 1 preceding
    ) as jockey_wins_3y
  from yearly_jockey yj
)

select
  jockey_cd,
  held_year_month,
  jockey_starts_3y,
  jockey_places_3y,
  jockey_wins_3y,
  case
    when jockey_starts_3y is null or jockey_starts_3y = 0 then null
    else jockey_places_3y::float / nullif(jockey_starts_3y, 0)
  end as jockey_place_rate_3y,
  ((jockey_places_3y + (0.213 * 10))::float / nullif(jockey_starts_3y + 10, 0)) as jockey_place_rate_3y_smooth,
  case
    when jockey_starts_3y is null or jockey_starts_3y = 0 then null
    else
      ln(
        least(greatest(jockey_places_3y::float / nullif(jockey_starts_3y, 0), 1e-6), 1 - 1e-6)
        / (1 - least(greatest(jockey_places_3y::float / nullif(jockey_starts_3y, 0), 1e-6), 1 - 1e-6))
      )
  end as jockey_place_rate_3y_logit,
  case
    when jockey_starts_3y is null or jockey_starts_3y = 0 then null
    else
      ln(
        least(greatest((jockey_places_3y + (0.213 * 10))::float / nullif(jockey_starts_3y + 10, 0), 1e-6), 1 - 1e-6)
        / (1 - least(greatest((jockey_places_3y + (0.213 * 10))::float / nullif(jockey_starts_3y + 10, 0), 1e-6), 1 - 1e-6))
      )
  end as jockey_place_rate_3y_logit_smooth
from yearly_jockey_roll
{% if is_incremental() %}
where held_year_month >= (select recalc_from_period from incremental_bounds)
{% endif %}
