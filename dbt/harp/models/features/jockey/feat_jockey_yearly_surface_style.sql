{{ config(
  materialized='incremental',
  unique_key=['jockey_cd', 'held_year_month', 'surface', 'running_style'],
  indexes=[{'columns': ['jockey_cd', 'held_year_month', 'surface', 'running_style']}],
  tags=['feature','monthly']
) }}

with incremental_bounds as (
  {{ monthly_incremental_bounds(this, history_years=3) }}
),

base as (
  select
    rie.jockey_cd,
    rie.held_year_month,
    rie.surface,
    frz.running_style,
    rie.is_place
  from {{ ref('int_race_entry_enriched') }} rie
  inner join {{ ref('feat_race_relative_z') }} frz
    on rie.race_id = frz.race_id
    and rie.kettonum = frz.kettonum
  where rie.held_year_month is not null
    and rie.jockey_cd is not null
    and rie.surface is not null
    and frz.running_style is not null
  {% if is_incremental() %}
    and rie.held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_jockey_surface_style as (
  select
    jockey_cd,
    held_year_month,
    surface,
    running_style,
    count(*) as starts,
    sum(is_place) as places
  from base
  group by
    jockey_cd,
    held_year_month,
    surface,
    running_style
),

yearly_jockey_surface_style_roll as (
  select
    yjss.*,
    sum(yjss.starts) over (
      partition by yjss.jockey_cd, yjss.surface, yjss.running_style
      order by yjss.held_year_month
      rows between 35 preceding and 1 preceding
    ) as jockey_surface_style_starts_3y,
    sum(yjss.places) over (
      partition by yjss.jockey_cd, yjss.surface, yjss.running_style
      order by yjss.held_year_month
      rows between 35 preceding and 1 preceding
    ) as jockey_surface_style_places_3y
  from yearly_jockey_surface_style yjss
)

select
  jockey_cd,
  held_year_month,
  surface,
  running_style,
  jockey_surface_style_starts_3y,
  jockey_surface_style_places_3y,
  case
    when jockey_surface_style_starts_3y is null or jockey_surface_style_starts_3y = 0 then null
    else jockey_surface_style_places_3y::float / nullif(jockey_surface_style_starts_3y, 0)
  end as jockey_surface_style_place_rate_3y,
  case
    when jockey_surface_style_starts_3y is null or jockey_surface_style_starts_3y = 0 then null
    else ((jockey_surface_style_places_3y + (0.213 * 10))::float / nullif(jockey_surface_style_starts_3y + 10, 0))
  end as jockey_surface_style_place_rate_3y_smooth
from yearly_jockey_surface_style_roll
{% if is_incremental() %}
where held_year_month >= (select recalc_from_period from incremental_bounds)
{% endif %}
