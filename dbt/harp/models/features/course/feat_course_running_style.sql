-- コースと脚質（直近5年の複勝率）
{{ config(
  materialized='incremental',
  unique_key=['held_year', 'jyo_cd', 'distance_m', 'surface', 'track_cd', 'running_style_cd'],
  indexes=[{'columns': ['held_year', 'jyo_cd', 'distance_m', 'surface', 'track_cd', 'running_style_cd']}],
  tags=['feature']
) }}

with incremental_bounds as (
  {{ yearly_incremental_bounds(this, history_years=5) }}
),

base as (
  select
    held_year,
    jyo_cd,
    distance_m,
    surface,
    track_cd,
    running_style_cd,
    is_place
  from {{ ref('int_race_entry_enriched') }}
  where held_year is not null
    and running_style_cd is not null
    and jyo_cd is not null
    and distance_m is not null
    and surface is not null
    and track_cd is not null
  {% if is_incremental() %}
    and held_year >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_course_style as (
  select
    held_year,
    jyo_cd,
    distance_m,
    surface,
    track_cd,
    running_style_cd,
    count(*) as starts,
    sum(is_place) as places
  from base
  group by
    held_year,
    jyo_cd,
    distance_m,
    surface,
    track_cd,
    running_style_cd
),

yearly_course_style_roll as (
  select
    ycs.*,
    sum(ycs.starts) over (
      partition by ycs.jyo_cd, ycs.distance_m, ycs.surface, ycs.track_cd, ycs.running_style_cd
      order by ycs.held_year
      rows between 5 preceding and 1 preceding
    ) as course_style_starts_5y,
    sum(ycs.places) over (
      partition by ycs.jyo_cd, ycs.distance_m, ycs.surface, ycs.track_cd, ycs.running_style_cd
      order by ycs.held_year
      rows between 5 preceding and 1 preceding
    ) as course_style_places_5y
  from yearly_course_style ycs
)

select
  held_year,
  jyo_cd,
  distance_m,
  surface,
  track_cd,
  running_style_cd,
  course_style_starts_5y,
  course_style_places_5y,
  course_style_places_5y::float / nullif(course_style_starts_5y, 0) as course_style_place_rate_5y
from yearly_course_style_roll
{% if is_incremental() %}
where held_year >= (select recalc_from_period from incremental_bounds)
{% endif %}
