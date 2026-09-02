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

  nullif(trim(syussotosu), '')::int as syussotosu,

  sibababacd,
  dirtbabacd,
  trim(harontimes3)::int / 10.0  as harontimes3,
  trim(harontimes4)::int / 10.0  as harontimes4,
  trim(harontimel3)::int / 10.0  as harontimel3,
  trim(harontimel4)::int / 10.0  as harontimel4,
  trackcd::int as track_cd

from {{ source('raw', 's_race') }}
where
  recordspec = 'RA'
  and datakubun = '7'