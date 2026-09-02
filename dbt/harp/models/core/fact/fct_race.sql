{{ config(
    materialized='table',
    schema='core',
    unique_key='race_id',
    on_schema_change='sync_all_columns'
) }}

with base as (
  select * ,
    case 
      when grade_cd = 'A' then '8'
      when grade_cd = 'B' then '7'
      when grade_cd = 'C' then '6'
      when grade_cd = 'D' then '5' 
      when grade_cd = 'E' then '5'
      else null
    end ::int as grade_code,
  
    case when track_cd >=10 and track_cd <=22 then 0
         when track_cd >=23 and track_cd <=29 then 1
    end ::int as surface,
    case
      when track_cd >=10 and track_cd <=22 then sibababacd
      when track_cd >=23 and track_cd <=29 then dirtbabacd
      else null
    end ::int as surface_condition,


    jyokencd5::int as jyoken_code
  from {{ ref('stg_n_race') }}
),

final as (
  select
    -- race_id: year+monthday+jyo+kaiji+nichiji+racenum
    concat(
      year,
      monthday,
      lpad(trim(jyocd), 2, '0'),
      lpad(kaiji::text, 2, '0'),
      lpad(nichiji::text, 2, '0'),
      lpad(racenum::text, 2, '0')
    )::bigint  as race_id,
    racenum as round,

    to_date(year || monthday, 'YYYYMMDD') as held_date,
    year::int as held_year,

    trim(concat_ws(' ', hondai, fukudai, kakko)) as name,

    nullif(trim(jyocd), '')::int as jyo_cd,
    kaiji,
    nichiji,
    racenum as race_num,
    surface,
    surface_condition,
    case when surface_condition in (3,4) then 3
         when surface_condition = 2 then 2
          when surface_condition = 1 then 1
    else null
    end as surface_condition_cd,

    -- 2歳戦＝1、3歳戦＝2、古馬＝0
    case
      when syubetu_cd = '11' then '1'
      when syubetu_cd = '12' then '2'
      else '0'
    end ::int as old_cd,

    case when course_kubun_cd = 'A' then 1
         when course_kubun_cd = 'B' then 2
         when course_kubun_cd = 'C' then 3
         when course_kubun_cd = 'D' then 4
         when course_kubun_cd = 'E' then 5
         else null
    end as course_kubun_cd,

    tenko_cd,
    jyuryo_cd,


    case
      when jyoken_code = 999 then grade_code
      when jyoken_code = 16 then 4
      when jyoken_code = 10 then 3
      when jyoken_code = 5 then 2
      when jyoken_code = 701 then 0
      when jyoken_code = null then null
      else 1
    end as race_level,
    kyori as distance_m,
    gradecd as grade_cd,

    TorokuTosu::int as num_starters,
    case
      when harontimes3 = 0 then null
      when kyori % 200 = 0 then harontimes3
      when kyori % 200 = 100 then (harontimes4+harontimes3)/2
      else harontimes3
    end as ten3f,
    nullif(harontimes4, 0) as ten4f,
    nullif(harontimel3, 0) as agari3f_race,
    nullif(harontimel4, 0) as agari4f_race,
    track_cd,
    hassotime,

    LapTime1+LapTime2+LapTime3+LapTime4+LapTime5+LapTime6+LapTime7+LapTime8+LapTime9+LapTime10+LapTime11+LapTime12+
    LapTime13+LapTime14+LapTime15+LapTime16+LapTime17+LapTime18 as race_time_sec,

    now() as updated_at

  from base
),

-- time_data as (

--   select
--     race_id,
--     time_sec
--   from {{ ref('fct_race_entry') }}
--   where result_order = 1
--   group by race_id, time_sec
-- ),

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
  final.*,
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
  c.course_cluster,
  ten3f - agari3f_race as race_pace,
  ntile(3) over (
      partition by final.jyo_cd, final.distance_m, final.surface, final.surface_condition_cd, final.track_cd
      order by final.ten3f nulls last
    ) as ten3f_ntile
from final
left join course_feature_map f
  on final.jyo_cd = f.jyo_cd
 and final.surface = f.surface
 and final.track_cd = f.track_cd
left join course_cluster_map c
  on final.jyo_cd = c.jyo_cd
 and final.distance_m = c.distance_m
 and final.surface = c.surface
 and final.track_cd = c.track_cd
where final.held_date >= '2008-01-01'


-- {% if is_incremental() %}
-- -- ざっくり増分：開催日で絞る（生データの更新特性次第で調整）
-- -- where to_date(year || monthday, 'YYYYMMDD') >= (select coalesce(max(held_date), '1900-01-01'::date) from {{ this }})
-- {% endif %}
