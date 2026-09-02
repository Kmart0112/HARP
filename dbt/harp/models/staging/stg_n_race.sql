{{ config(materialized='view') }}

select
  recordspec,
  datakubun,
  year,
  monthday,
  jyocd,
  kaiji::int as kaiji,
  nichiji::int as nichiji,
  racenum::int as racenum,

  nullif(trim(hondai), '') as hondai,
  nullif(trim(fukudai), '') as fukudai,
  nullif(trim(kakko), '') as kakko,

  nullif(trim(gradecd), '') as gradecd,

  syubetuCD as syubetu_cd,

  kyori::int as kyori,
  gradecd as grade_cd,
  jyokencd1,
  jyokencd2,
  jyokencd3,
  jyokencd4,
  jyokencd5,
  TenkoCD::int as tenko_cd,
  JyuryoCD::int as jyuryo_cd,


  CourseKubunCD as course_kubun_cd,

  case
    when hassotimebefore = '0000' then hassotime
    else hassotimebefore
  end ::time as hassotime ,

  nullif(trim(TorokuTosu), '')::int as TorokuTosu,

  sibababacd,
  dirtbabacd,
  trim(harontimes3)::int / 10.0  as harontimes3,
  trim(harontimes4)::int / 10.0  as harontimes4,
  trim(harontimel3)::int / 10.0  as harontimel3,
  trim(harontimel4)::int / 10.0  as harontimel4,
  trackcd::int as track_cd,

  LapTime1::int / 10.0 as LapTime1,
  LapTime2::int / 10.0 as LapTime2,
  LapTime3::int / 10.0 as LapTime3,
  LapTime4::int / 10.0 as LapTime4,
  LapTime5::int / 10.0 as LapTime5,
  LapTime6::int / 10.0 as LapTime6,
  LapTime7::int / 10.0 as LapTime7,
  LapTime8::int / 10.0 as LapTime8,
  laptime9::int / 10.0 as laptime9,
  laptime10::int / 10.0 as laptime10,
  laptime11::int / 10.0 as laptime11,
  laptime12::int / 10.0 as laptime12,
  laptime13::int / 10.0 as laptime13,
  laptime14::int / 10.0 as laptime14,
  laptime15::int / 10.0 as laptime15,
  laptime16::int / 10.0 as laptime16,
  laptime17::int / 10.0 as laptime17,
  laptime18::int / 10.0 as laptime18


  

from {{ source('raw', 'n_race') }}
where
  recordspec = 'RA'
  and datakubun in ('1', '2','3','4','5','6','7')
