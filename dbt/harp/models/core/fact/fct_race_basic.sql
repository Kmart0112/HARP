{{ config(
  materialized='incremental',
  unique_key='race_id',
  on_schema_change='sync_all_columns',
  tags=['race_week_static']
) }}

with base as (
  select
    *,
    case
      when grade_cd = 'A' then 8
      when grade_cd = 'B' then 7
      when grade_cd = 'C' then 6
      when grade_cd = 'D' then 5
      when grade_cd = 'E' then 5
      else null
    end as grade_code,
    case
      when track_cd between 10 and 22 then 0
      when track_cd between 23 and 29 then 1
      else null
    end::int as surface,
    case
      when track_cd between 10 and 22 then sibababacd
      when track_cd between 23 and 29 then dirtbabacd
      else null
    end::int as surface_condition,
    jyokencd5::int as jyoken_code
  from {{ ref('stg_n_race') }}
),

normalized as (
  select
    concat(
      year,
      monthday,
      lpad(trim(jyocd), 2, '0'),
      lpad(kaiji::text, 2, '0'),
      lpad(nichiji::text, 2, '0'),
      lpad(racenum::text, 2, '0')
    )::bigint as race_id,
    racenum as round,
    to_date(year || monthday, 'YYYYMMDD') as held_date,
    year::int as held_year,
    date_trunc('month', to_date(year || monthday, 'YYYYMMDD')) as held_year_month,
    trim(concat_ws(' ', hondai, fukudai, kakko)) as race_name,
    nullif(trim(jyocd), '')::int as jyo_cd,
    kaiji,
    nichiji,
    racenum as race_num,
    surface,
    surface_condition as base_surface_condition,
    case
      when surface_condition in (3, 4) then 3
      when surface_condition = 2 then 2
      when surface_condition = 1 then 1
      else null
    end as base_surface_condition_cd,
    tenko_cd as base_weather_cd,
    jyuryo_cd as base_jyuryo_cd,
    case
      when syubetu_cd = '11' then 1
      when syubetu_cd = '12' then 2
      else 0
    end::int as old_cd,
    case
      when course_kubun_cd = 'A' then 1
      when course_kubun_cd = 'B' then 2
      when course_kubun_cd = 'C' then 3
      when course_kubun_cd = 'D' then 4
      when course_kubun_cd = 'E' then 5
      else null
    end as course_kubun_cd,
    case
      when jyoken_code = 999 then grade_code
      when jyoken_code = 16 then 4
      when jyoken_code = 10 then 3
      when jyoken_code = 5 then 2
      when jyoken_code = 701 then 0
      when jyoken_code is null then null
      else 1
    end as race_level,
    kyori as distance_m,
    gradecd as grade_cd,
    torokutosu::int as planned_num_starters,
    track_cd,
    hassotime,
    now() as updated_at
  from base
),

course_cluster_map as (
  select
    jyo_cd::int as jyo_cd,
    distance_m::int as distance_m,
    surface::int as surface,
    track_cd::int as track_cd,
    cluster::int as course_cluster
  from {{ ref('course_cluster_map') }}
),

course_feature_map as (
  select
    jyo_cd::int as jyo_cd,
    surface::int as surface,
    track_cd::int as track_cd,
    jyo_name,
    surface_name,
    track_cd_label,
    turn_direction,
    turn_direction_cd::int as turn_direction_cd,
    course_variant,
    straight_distance_m::float as straight_distance_m,
    elevation_diff_m::float as elevation_diff_m,
    has_slope::boolean as has_slope,
    has_homestretch_slope::boolean as has_homestretch_slope,
    has_uphill_finish::boolean as has_uphill_finish,
    slope_feature_ja,
    source_url
  from {{ ref('course_feature_map') }}
)

select
  n.*,
  f.jyo_name,
  f.surface_name,
  f.track_cd_label,
  f.turn_direction,
  f.turn_direction_cd,
  f.course_variant,
  f.straight_distance_m,
  f.elevation_diff_m,
  f.has_slope,
  f.has_homestretch_slope,
  f.has_uphill_finish,
  f.slope_feature_ja,
  f.source_url,
  c.course_cluster
from normalized n
left join course_feature_map f
  on n.jyo_cd = f.jyo_cd
 and n.surface = f.surface
 and n.track_cd = f.track_cd
left join course_cluster_map c
  on n.jyo_cd = c.jyo_cd
 and n.distance_m = c.distance_m
 and n.surface = c.surface
 and n.track_cd = c.track_cd
where n.held_date >= '2008-01-01'
{% if is_incremental() %}
  and n.held_date between
    '{{ var("race_from_date", "1900-01-01") }}'::date
    and '{{ var("race_to_date", "2999-12-31") }}'::date
{% endif %}
