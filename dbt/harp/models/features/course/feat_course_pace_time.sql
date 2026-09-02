-- コース条件別の過去タイム集計（年次×過去5年）
{{ config(
  materialized='incremental',
  unique_key=['held_year', 'jyo_cd', 'distance_m', 'surface', 'track_cd', 'surface_condition_cd', 'ten3f_ntile'],
  tags=['feature']
) }}

with incremental_bounds as (
  {{ yearly_incremental_bounds(this, history_years=5) }}
),

races as (
  select
    held_year,
    jyo_cd,
    distance_m,
    track_cd,
    surface,
    surface_condition_cd,
    race_time_sec,
    agari3f_race as agari3f,
    race_pace,
    ten3f,
    ten4f,
    ten3f_ntile
  from {{ ref('fct_race') }}
  where held_year is not null
  {% if is_incremental() %}
    and held_year >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_course_time as (
  select
    held_year,
    jyo_cd,
    distance_m,
    track_cd,
    surface,
    surface_condition_cd,
    ten3f_ntile,
    count(*) as race_count,
    sum(race_time_sec) as sum_time_sec,
    sum(race_time_sec * race_time_sec) as sum_time_sec_sq,
    sum(agari3f) as sum_agari3f,
    sum(agari3f * agari3f) as sum_agari3f_sq,
    sum(race_pace) as sum_race_pace,
    sum(race_pace * race_pace) as sum_race_pace_sq,
    sum(ten3f) as sum_ten3f,
    sum(ten3f * ten3f) as sum_ten3f_sq,
    sum(ten4f) as sum_ten4f,
    sum(ten4f * ten4f) as sum_ten4f_sq
  from races
  group by
    held_year,
    jyo_cd,
    distance_m,
    track_cd,
    surface,
    surface_condition_cd,
    ten3f_ntile
),

yearly_course_time_cum as (
  select
    yc.*,
    sum(yc.race_count) over (
      partition by yc.jyo_cd, yc.distance_m, yc.track_cd, yc.surface, yc.surface_condition_cd, yc.ten3f_ntile
      order by yc.held_year
      rows between 5 preceding and 1 preceding
    ) as race_count_5y,
    sum(yc.sum_time_sec) over (
      partition by yc.jyo_cd, yc.distance_m, yc.track_cd, yc.surface, yc.surface_condition_cd, yc.ten3f_ntile
      order by yc.held_year
      rows between 5 preceding and 1 preceding
    ) as sum_time_sec_5y,
    sum(yc.sum_time_sec_sq) over (
      partition by yc.jyo_cd, yc.distance_m, yc.track_cd, yc.surface, yc.surface_condition_cd, yc.ten3f_ntile
      order by yc.held_year
      rows between 5 preceding and 1 preceding
    ) as sum_time_sec_sq_5y,
    sum(yc.sum_agari3f) over (
      partition by yc.jyo_cd, yc.distance_m, yc.track_cd, yc.surface, yc.surface_condition_cd, yc.ten3f_ntile
      order by yc.held_year
      rows between 5 preceding and 1 preceding
    ) as sum_agari3f_5y,
    sum(yc.sum_agari3f_sq) over (
      partition by yc.jyo_cd, yc.distance_m, yc.track_cd, yc.surface, yc.surface_condition_cd, yc.ten3f_ntile
      order by yc.held_year
      rows between 5 preceding and 1 preceding
    ) as sum_agari3f_sq_5y,
    sum(yc.sum_race_pace) over (
      partition by yc.jyo_cd, yc.distance_m, yc.track_cd, yc.surface, yc.surface_condition_cd, yc.ten3f_ntile
      order by yc.held_year
      rows between 5 preceding and 1 preceding
    ) as sum_race_pace_5y,
    sum(yc.sum_race_pace_sq) over (
      partition by yc.jyo_cd, yc.distance_m, yc.track_cd, yc.surface, yc.surface_condition_cd, yc.ten3f_ntile
      order by yc.held_year
      rows between 5 preceding and 1 preceding
    ) as sum_race_pace_sq_5y,
    sum(yc.sum_ten3f) over (
      partition by yc.jyo_cd, yc.distance_m, yc.track_cd, yc.surface, yc.surface_condition_cd, yc.ten3f_ntile
      order by yc.held_year
      rows between 5 preceding and 1 preceding
    ) as sum_ten3f_5y,
    sum(yc.sum_ten3f_sq) over (
      partition by yc.jyo_cd, yc.distance_m, yc.track_cd, yc.surface, yc.surface_condition_cd, yc.ten3f_ntile
      order by yc.held_year
      rows between 5 preceding and 1 preceding
    ) as sum_ten3f_sq_5y,
    sum(yc.sum_ten4f) over (
      partition by yc.jyo_cd, yc.distance_m, yc.track_cd, yc.surface, yc.surface_condition_cd, yc.ten3f_ntile
      order by yc.held_year
      rows between 5 preceding and 1 preceding
    ) as sum_ten4f_5y,
    sum(yc.sum_ten4f_sq) over (
      partition by yc.jyo_cd, yc.distance_m, yc.track_cd, yc.surface, yc.surface_condition_cd, yc.ten3f_ntile
      order by yc.held_year
      rows between 5 preceding and 1 preceding
    ) as sum_ten4f_sq_5y
  from yearly_course_time yc
)

select
  held_year,
  jyo_cd,
  distance_m,
  surface,
  track_cd,
  surface_condition_cd,
  ten3f_ntile,
  race_count,
  (sum_time_sec / nullif(race_count, 0))::float as avg_time_sec,
  (sum_agari3f / nullif(race_count, 0))::float as avg_agari3f,
  (sum_race_pace / nullif(race_count, 0))::float as avg_race_pace,
  (sum_ten3f / nullif(race_count, 0))::float as avg_ten3f,
  (sum_ten4f / nullif(race_count, 0))::float as avg_ten4f,
  race_count_5y,
  (sum_time_sec_5y / nullif(race_count_5y, 0))::float as avg_time_sec_5y,
  (sum_agari3f_5y / nullif(race_count_5y, 0))::float as avg_agari3f_5y,
  (sum_race_pace_5y / nullif(race_count_5y, 0))::float as avg_race_pace_5y,
  (sum_ten3f_5y / nullif(race_count_5y, 0))::float as avg_ten3f_5y,
  (sum_ten4f_5y / nullif(race_count_5y, 0))::float as avg_ten4f_5y,
  case
    when race_count_5y > 0 then sqrt((sum_time_sec_sq_5y / race_count_5y) - power(sum_time_sec_5y / race_count_5y, 2))
  end::float as std_time_sec_5y,
  case
    when race_count_5y > 0 then sqrt((sum_agari3f_sq_5y / race_count_5y) - power(sum_agari3f_5y / race_count_5y, 2))
  end::float as std_agari3f_5y,
  case
    when race_count_5y > 0 then sqrt((sum_race_pace_sq_5y / race_count_5y) - power(sum_race_pace_5y / race_count_5y, 2))
  end::float as std_race_pace_5y,
  case
    when race_count_5y > 0 then sqrt((sum_ten3f_sq_5y / race_count_5y) - power(sum_ten3f_5y / race_count_5y, 2))
  end::float as std_ten3f_5y,
  case
    when race_count_5y > 0 then sqrt((sum_ten4f_sq_5y / race_count_5y) - power(sum_ten4f_5y / race_count_5y, 2))
  end::float as std_ten4f_5y
from yearly_course_time_cum
{% if is_incremental() %}
where held_year >= (select recalc_from_period from incremental_bounds)
{% endif %}
