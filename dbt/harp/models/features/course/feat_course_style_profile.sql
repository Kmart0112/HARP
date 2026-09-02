-- コースと脚質
{{ config(
  materialized='incremental',
  unique_key=['held_year', 'jyo_cd', 'distance_m', 'surface', 'track_cd'],
  indexes=[{'columns': ['held_year', 'jyo_cd', 'distance_m', 'surface', 'track_cd']}],
  tags=['feature']
) }}

with incremental_bounds as (
  {{ yearly_incremental_bounds(this, history_years=5) }}
),

races as (
  select
    race_id,
    held_year,
    jyo_cd,
    distance_m,
    surface,
    track_cd,
    result_order,
    corner3_pos
  from {{ ref('int_race_entry_enriched') }}
  {% if is_incremental() %}
    where held_year >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

top3 as (
  select
    held_year,
    jyo_cd,
    distance_m,
    surface,
    track_cd,
    corner3_pos
  from races
  where result_order between 1 and 3
),

yearly_course_top3 as (
  select
    held_year,
    jyo_cd,
    distance_m,
    surface,
    track_cd,
    count(*) as top3_count,
    sum(corner3_pos) as sum_top3_corner3_pos,
    avg(corner3_pos) as top3_corner3_pos_avg,
    var_samp(corner3_pos) as top3_corner3_pos_var
  from top3
  group by held_year, jyo_cd, distance_m, surface, track_cd
),

yearly_course_top3_cum as (
  select
    yc.held_year,
    yc.jyo_cd,
    yc.distance_m,
    yc.surface,
    yc.track_cd,
    yc.top3_corner3_pos_avg,
    yc.top3_corner3_pos_var,
    sum(yc.sum_top3_corner3_pos) over (
      partition by yc.jyo_cd, yc.distance_m, yc.surface, yc.track_cd
      order by yc.held_year
      rows between 5 preceding and 1 preceding
    ) as sum_top3_corner3_pos_5y,
    sum(yc.top3_count) over (
      partition by yc.jyo_cd, yc.distance_m, yc.surface, yc.track_cd
      order by yc.held_year
      rows between 5 preceding and 1 preceding
    ) as top3_count_5y,
    avg(yc.top3_corner3_pos_avg) over (
      partition by yc.jyo_cd, yc.distance_m, yc.surface, yc.track_cd
      order by yc.held_year
      rows between 5 preceding and 1 preceding
    ) as top3_corner3_pos_avg_5y,
    avg(yc.top3_corner3_pos_var) over (
      partition by yc.jyo_cd, yc.distance_m, yc.surface, yc.track_cd
      order by yc.held_year
      rows between 5 preceding and 1 preceding
    ) as top3_corner3_pos_var_5y
  from yearly_course_top3 yc
)

select
  held_year,
  jyo_cd,
  distance_m,
  surface,
  track_cd,
  nullif(sum_top3_corner3_pos_5y / nullif(top3_count_5y, 0), 0) as top3_corner3_pos_avg_5y,
  top3_corner3_pos_var_5y
from yearly_course_top3_cum
{% if is_incremental() %}
where held_year >= (select recalc_from_period from incremental_bounds)
{% endif %}
