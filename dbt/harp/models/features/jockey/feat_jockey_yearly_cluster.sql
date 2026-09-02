-- ジョッキー×コースクラスタ別の年次成績（過去3年移動平均）
{{ config(
  materialized='incremental',
  unique_key=['jockey_cd', 'held_year_month', 'course_cluster'],
  indexes=[{'columns': ['jockey_cd', 'held_year_month', 'course_cluster']}],
  tags=['feature','monthly']
) }}

with incremental_bounds as (
  {{ monthly_incremental_bounds(this, history_years=3) }}
),

base as (
  select
    jockey_cd,
    held_year_month,
    course_cluster,
    is_place
  from {{ ref('int_race_entry_enriched') }}
  where held_year_month is not null
    and jockey_cd is not null
    and course_cluster is not null
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_jockey_cluster as (
  select
    jockey_cd,
    held_year_month,
    course_cluster,
    count(*) as starts,
    sum(is_place) as places
  from base
  group by
    jockey_cd,
    held_year_month,
    course_cluster
),

yearly_jockey_cluster_roll as (
  select
    yjc.*,
    sum(yjc.starts) over (
      partition by yjc.jockey_cd, yjc.course_cluster
      order by yjc.held_year_month
      rows between 35 preceding and 1 preceding
    ) as jockey_cluster_starts_3y,
    sum(yjc.places) over (
      partition by yjc.jockey_cd, yjc.course_cluster
      order by yjc.held_year_month
      rows between 35 preceding and 1 preceding
    ) as jockey_cluster_places_3y
  from yearly_jockey_cluster yjc
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
  course_cluster,
  jockey_cluster_starts_3y,
  jockey_cluster_places_3y,
  case
    when jockey_cluster_starts_3y is null or jockey_cluster_starts_3y = 0 then null
    else jockey_cluster_places_3y::float / nullif(jockey_cluster_starts_3y, 0)
  end as jockey_cluster_place_rate_3y,
  ((jockey_cluster_places_3y + (0.213 * 10))::float / nullif(jockey_cluster_starts_3y + 10, 0)) as jockey_cluster_place_rate_3y_smooth,
  case
    when ((jockey_cluster_places_3y + (0.213 * 10))::float / nullif(jockey_cluster_starts_3y + 10, 0)) is null
      or jyo.jockey_place_rate_3y_smooth is null then null
    else
      ln(
        least(greatest(((jockey_cluster_places_3y + (0.213 * 10))::float / nullif(jockey_cluster_starts_3y + 10, 0)), 1e-6), 1 - 1e-6)
        / (1 - least(greatest(((jockey_cluster_places_3y + (0.213 * 10))::float / nullif(jockey_cluster_starts_3y + 10, 0)), 1e-6), 1 - 1e-6))
      )
      -
      ln(
        least(greatest(jyo.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6)
        / (1 - least(greatest(jyo.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6))
      )
  end as jockey_cluster_avg_diff_logit_smooth
from yearly_jockey_cluster_roll yjcr
left join jockey_yearly_overall jyo
  using (jockey_cd, held_year_month)
{% if is_incremental() %}
where held_year_month >= (select recalc_from_period from incremental_bounds)
{% endif %}
