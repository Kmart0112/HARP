{{ config(
  materialized='incremental',
  unique_key=['jockey_cd', 'held_year_month', 'running_style_cd'],
  indexes=[{'columns': ['jockey_cd', 'held_year_month', 'running_style_cd']}],
  tags=['feature','monthly']
) }}

with incremental_bounds as (
  {{ monthly_incremental_bounds(this, history_years=3) }}
),

base as (
  select
    jockey_cd,
    running_style_cd,
    held_year_month,
    is_place
  from {{ ref('int_race_entry_enriched') }}
  where held_year_month is not null
    and jockey_cd is not null
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_jockey_style as (
  select
    jockey_cd,
    held_year_month,
    running_style_cd,
    count(*) as starts,
    sum(is_place) as places
  from base
  group by
    jockey_cd,
    held_year_month,
    running_style_cd
),

yearly_overall_style as (
  select
    held_year_month,
    running_style_cd,
    count(*) as starts,
    sum(is_place) as places
  from base
  group by
    held_year_month,
    running_style_cd
),

yearly_jockey_style_cum as (
  select
    yjs.*,
    sum(yjs.starts) over (
      partition by yjs.jockey_cd, yjs.running_style_cd
      order by yjs.held_year_month
      rows between 35 preceding and 1 preceding
    ) as jockey_style_starts_3y,
    sum(yjs.places) over (
      partition by yjs.jockey_cd, yjs.running_style_cd
      order by yjs.held_year_month
      rows between 35 preceding and 1 preceding
    ) as jockey_style_places_3y
  from yearly_jockey_style yjs
),

overall_cum as (
  select
    yos.*,
    sum(yos.starts) over (
      partition by yos.running_style_cd
      order by yos.held_year_month
      rows between 35 preceding and 1 preceding
    ) as overall_style_starts_3y,
    sum(yos.places) over (
      partition by yos.running_style_cd
      order by yos.held_year_month
      rows between 35 preceding and 1 preceding
    ) as overall_style_places_3y
  from yearly_overall_style yos
),

overall_style_place_rate as (
  select
    held_year_month,
    running_style_cd,
    overall_style_starts_3y,
    overall_style_places_3y,
    overall_style_places_3y::float / nullif(overall_style_starts_3y, 0) as overall_style_place_rate_3y,
    ((overall_style_places_3y + (0.213 * 10))::float / nullif(overall_style_starts_3y + 10, 0)) as overall_style_place_rate_3y_smooth
  from overall_cum
),

jockey_yearly_overall as (
  select
    jockey_cd,
    held_year_month,
    jockey_place_rate_3y_smooth
  from {{ ref('feat_jockey_yearly_overall') }}
)

select
  jockey_cd,
  held_year_month,
  running_style_cd,
  jockey_style_starts_3y,
  jockey_style_places_3y,
  jockey_style_places_3y::float / nullif(jockey_style_starts_3y, 0) as jockey_style_place_rate_3y,
  ((jockey_style_places_3y + (0.213 * 10))::float / nullif(jockey_style_starts_3y + 10, 0)) as jockey_style_place_rate_3y_smooth,
  ((jockey_style_places_3y + (ospr.overall_style_place_rate_3y_smooth * 10))::float / nullif(jockey_style_starts_3y + 10, 0)) as jockey_style_place_rate_3y_style_prior_smooth,
  (jockey_style_places_3y::float / nullif(jockey_style_starts_3y, 0)) / ospr.overall_style_place_rate_3y as relative_place_rate_3y,
  (((jockey_style_places_3y + (0.213 * 10))::float / nullif(jockey_style_starts_3y + 10, 0)) / ospr.overall_style_place_rate_3y_smooth) as relative_place_rate_3y_smooth,
  case
    when ((jockey_style_places_3y + (0.213 * 10))::float / nullif(jockey_style_starts_3y + 10, 0)) is null
      or ospr.overall_style_place_rate_3y_smooth is null then null
    else
      ln(
        least(greatest(((jockey_style_places_3y + (0.213 * 10))::float / nullif(jockey_style_starts_3y + 10, 0)), 1e-6), 1 - 1e-6)
        / (1 - least(greatest(((jockey_style_places_3y + (0.213 * 10))::float / nullif(jockey_style_starts_3y + 10, 0)), 1e-6), 1 - 1e-6))
      )
      -
      ln(
        least(greatest(ospr.overall_style_place_rate_3y_smooth, 1e-6), 1 - 1e-6)
        / (1 - least(greatest(ospr.overall_style_place_rate_3y_smooth, 1e-6), 1 - 1e-6))
      )
  end as jockey_style_base_diff_logit_smooth,
  case
    when ((jockey_style_places_3y + (0.213 * 10))::float / nullif(jockey_style_starts_3y + 10, 0)) is null
      or jyo.jockey_place_rate_3y_smooth is null then null
    else
      ln(
        least(greatest(((jockey_style_places_3y + (0.213 * 10))::float / nullif(jockey_style_starts_3y + 10, 0)), 1e-6), 1 - 1e-6)
        / (1 - least(greatest(((jockey_style_places_3y + (0.213 * 10))::float / nullif(jockey_style_starts_3y + 10, 0)), 1e-6), 1 - 1e-6))
      )
      -
      ln(
        least(greatest(jyo.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6)
        / (1 - least(greatest(jyo.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6))
      )
  end as jockey_style_avg_diff_logit_smooth
from yearly_jockey_style_cum yjsc
join overall_style_place_rate ospr
  using (held_year_month, running_style_cd)
left join jockey_yearly_overall jyo
  using (jockey_cd, held_year_month)
{% if is_incremental() %}
where held_year_month >= (select recalc_from_period from incremental_bounds)
{% endif %}
