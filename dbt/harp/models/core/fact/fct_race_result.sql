{{ config(
  materialized='table',
  tags=['post_race']
) }}

with base as (
  select
    *,
    case
      when track_cd between 10 and 22 then 0
      when track_cd between 23 and 29 then 1
      else null
    end::int as surface,
    case
      when track_cd between 10 and 22 then sibababacd
      when track_cd between 23 and 29 then dirtbabacd
      else null
    end::int as surface_condition
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
    to_date(year || monthday, 'YYYYMMDD') as held_date,
    nullif(harontimes3, 0) as ten3f_raw,
    nullif(harontimes4, 0) as ten4f,
    nullif(harontimel3, 0) as agari3f_race,
    nullif(harontimel4, 0) as agari4f_race,
    case
      when harontimes3 = 0 then null
      when kyori % 200 = 0 then harontimes3
      when kyori % 200 = 100 then (harontimes4 + harontimes3) / 2
      else harontimes3
    end as ten3f,
    laptime1 + laptime2 + laptime3 + laptime4 + laptime5 + laptime6
      + laptime7 + laptime8 + laptime9 + laptime10 + laptime11 + laptime12
      + laptime13 + laptime14 + laptime15 + laptime16 + laptime17 + laptime18
      as race_time_sec,
    tenko_cd as final_weather_cd,
    jyuryo_cd as final_jyuryo_cd,
    surface_condition as final_surface_condition,
    case
      when surface_condition in (3, 4) then 3
      when surface_condition = 2 then 2
      when surface_condition = 1 then 1
      else null
    end as final_surface_condition_cd,
    nullif(trim(jyocd), '')::int as jyo_cd,
    kyori as distance_m,
    surface,
    track_cd
  from base
),

final as (
  select
    *,
    ten3f - agari3f_race as race_pace
  from normalized
  where held_date >= '2008-01-01'
)

select
  final.*,
  ntile(3) over (
    partition by jyo_cd, distance_m, surface, final_surface_condition_cd, track_cd
    order by ten3f nulls last
  ) as ten3f_ntile,
  now() as updated_at
from final
