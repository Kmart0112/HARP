{{ config(materialized='view') }}

with src as (
  select
  *,
    -- race_id: races と同一ロジックにすること！
    concat(
      trim(year),
      lpad(trim(monthday), 4, '0'),
      lpad(trim(jyocd), 2, '0'),
      lpad(trim(kaiji), 2, '0'),
      lpad(trim(nichiji), 2, '0'),
      lpad(trim(racenum), 2, '0')
    )::bigint as race_id,

    nullif(trim(barei), '')::int as age,

    to_date(year || monthday, 'YYYYMMDD') as held_date,

    nullif(trim(ijyocd), '0') as ijyo_cd,

    nullif(nullif(trim(bataijyu), ''), '0')::int as h_weight,

    nullif(trim(futan), '')::int / 10.0 as kinryo,

    case
      when nullif(trim(ZogenSa), '') is null then null
      when trim(ZogenSa) = '000' then 0
      when zogenfugo = '+' then trim(ZogenSa)::int
      when zogenfugo = '-' then 0 - (trim(ZogenSa)::int)
      else null
    end as weight_change,

    -- 馬番（レース内の識別子として十分）
    nullif(trim(umaban), '') as horse_number_raw,

    -- 人気
    nullif(nullif(trim(ninki), ''), '0') as popularity_raw,

    -- 確定着順（基本これを使う）
    nullif(nullif(trim(kakuteijyuni), ''), '0') as result_order_raw,

    -- 除外/取消などが欲しければ後で使える
    -- nullif(trim(ijyocd), '0') as ijyo_cd,
    nullif(nullif(trim(jyuni1c), ''), '0')::int as rank_1c,
    nullif(nullif(trim(jyuni2c), ''), '0')::int as rank_2c,
    nullif(nullif(trim(jyuni3c), ''), '0')::int as rank_3c,
    nullif(nullif(trim(jyuni4c), ''), '0')::int as rank_4c,
    nullif(trim(harontimel3), '')::int / 10.0 as agari3f,
    nullif(trim(harontimel4), '')::int / 10.0 as agari4f,
    -- case
    --   when trim(timediff) = '999' then null
    --   else nullif(trim(timediff), '')::int / 10.0
    -- end as timediff,

    case
      when nullif(trim("time"), '') is null then null
      else (
        substring("time" from 1 for 1)::int * 60   -- 分
        + substring("time" from 2 for 2)::int       -- 秒
        + substring("time" from 4 for 1)::int / 10.0 -- 1/10秒
      )
    end as time_sec,

    nullif(trim(tozaicd), '')::int as tozai_cd,
    nullif(trim(kisyucode), '')::int as jockey_cd,
    nullif(trim(chokyosicode), '')::int as trainer_cd

  from {{ source('raw', 's_uma_race') }}
  where trim(jyocd) ~ '^[0-9]+$'
)

select
  race_id,
  held_date,
  datakubun,
  kettonum,
  umaban,
  src.age as age,
  h_weight,
  weight_change,
  kinryo,
  tozai_cd,
  jockey_cd,
  trainer_cd,
  ijyo_cd,
  bamei as horse_name,

  -- int化（空文字は null 扱い）
  cast(horse_number_raw as integer) as horse_number,
  nullif(trim(wakuban), '')::int as gate_number,
  cast(popularity_raw as integer) as popularity,
  cast(result_order_raw as integer) as result_order,
  rank_1c,
  rank_2c,
  rank_3c,
  rank_4c,
  agari3f,
  agari4f,
--   timediff as time_diff,
  nullif(time_sec, 0) as time_sec,
  result_order_raw is not null as has_result

from src
