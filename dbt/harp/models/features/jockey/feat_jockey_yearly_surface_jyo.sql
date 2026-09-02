{{ config(
  materialized='incremental',
  unique_key=['jockey_cd', 'held_year_month', 'surface', 'jyo_cd'],
  indexes=[{'columns': ['jockey_cd', 'held_year_month', 'surface', 'jyo_cd']}],
  tags=['feature','monthly']
) }}

with incremental_bounds as (
  {{ monthly_incremental_bounds(this, history_years=3) }}
),

base as (
  select
    jockey_cd,
    held_year_month,
    surface,
    jyo_cd,
    is_place
  from {{ ref('int_race_entry_enriched') }}
  where held_year_month is not null
    and jockey_cd is not null
    and surface is not null
    and jyo_cd is not null
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_jockey_surface_jyo as (
  select
    jockey_cd,
    held_year_month,
    surface,
    jyo_cd,
    count(*) as starts,
    sum(is_place) as places
  from base
  group by
    jockey_cd,
    held_year_month,
    surface,
    jyo_cd
),

yearly_jockey_surface_jyo_roll as (
  select
    yjsj.*,
    sum(yjsj.starts) over (
      partition by yjsj.jockey_cd, yjsj.surface, yjsj.jyo_cd
      order by yjsj.held_year_month
      rows between 35 preceding and 1 preceding
    ) as jockey_surface_jyo_starts_3y,
    sum(yjsj.places) over (
      partition by yjsj.jockey_cd, yjsj.surface, yjsj.jyo_cd
      order by yjsj.held_year_month
      rows between 35 preceding and 1 preceding
    ) as jockey_surface_jyo_places_3y
  from yearly_jockey_surface_jyo yjsj
)

select
  jockey_cd,
  held_year_month,
  surface,
  jyo_cd,
  jockey_surface_jyo_starts_3y,
  jockey_surface_jyo_places_3y,
  case
    when jockey_surface_jyo_starts_3y is null or jockey_surface_jyo_starts_3y = 0 then null
    else jockey_surface_jyo_places_3y::float / nullif(jockey_surface_jyo_starts_3y, 0)
  end as jockey_surface_jyo_place_rate_3y,
  case
    when jockey_surface_jyo_starts_3y is null or jockey_surface_jyo_starts_3y = 0 then null
    else ((jockey_surface_jyo_places_3y + (0.213 * 10))::float / nullif(jockey_surface_jyo_starts_3y + 10, 0))
  end as jockey_surface_jyo_place_rate_3y_smooth
from yearly_jockey_surface_jyo_roll
{% if is_incremental() %}
where held_year_month >= (select recalc_from_period from incremental_bounds)
{% endif %}
