{{ config(materialized='table', tags=['prd']) }}

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
    nullif(trim(sexcd), '0')::int as sex_cd,

    bamei as horse_name,
    nullif(trim(DMJyuni), '0')::int as dm_rank,

    nullif(trim(barei), '')::int as age,

    to_date(year || monthday, 'YYYYMMDD') as held_date,

    nullif(ijyocd,'0') as ijyo_cd,

    nullif(trim(bataijyu), '')::int as h_weight,

    nullif(trim(futan), '')::int/10.0 as kinryo,

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
    nullif(trim(ijyocd), '0') as ijyocd,
    nullif(nullif(trim(jyuni1c), ''), '0')::int as rank_1c,
    nullif(nullif(trim(jyuni2c), ''), '0')::int as rank_2c,
    nullif(nullif(trim(jyuni3c), ''), '0')::int as rank_3c,
    nullif(nullif(trim(jyuni4c), ''), '0')::int as rank_4c,
    nullif(trim(harontimel3), '')::int / 10.0 as agari3f,
    nullif(trim(harontimel4), '')::int / 10.0 as agari4f,
    case
      when trim(timediff) = '999' then null
      else nullif(trim(timediff), '')::int / 10.0
    end as time_diff_raw,

    case
      when nullif(trim("time"), '') is null then null
      else (
        substring("time" from 1 for 1)::int * 60   -- 分
        + substring("time" from 2 for 2)::int       -- 秒
        + substring("time" from 4 for 1)::int / 10.0 -- 1/10秒
      )
    end as time_sec,
    KyakusituKubun ::int as running_style_cd,
    blinker::int as blinker_cd

  from {{ source('raw', 'n_uma_race') }}
)

select
  race_id,
  kettonum ::bigint,
  horse_name,
  src.age as age,
  h_weight,
  weight_change,
  dm_rank,
  sex_cd,
  kinryo,
  tozaicd::int as tozai_cd,
  kisyucode::int as jockey_cd,
  case
    when KisyuRyakusyo = '武豊' then 1
    when KisyuRyakusyo = 'ルメール' then 2
    when KisyuRyakusyo = '川田将雅' then 3
    when KisyuRyakusyo = '戸崎圭太' then 4
    when KisyuRyakusyo = '丹内祐次' then 5
    when KisyuRyakusyo = '北村友一' then 6
    when KisyuRyakusyo = '横山武史' then 7
    when KisyuRyakusyo = '岩田望来' then 8
    when KisyuRyakusyo = '津村明秀' then 9
    when KisyuRyakusyo = '松山弘平' then 10
    when KisyuRyakusyo = '三浦皇成' then 11
    when KisyuRyakusyo = '池添謙一' then 12
    else 0
  end as jockey_cat,
  
  ChokyosiCode::int as trainer_cd,


  -- int化（空文字は null 扱い）
  cast(horse_number_raw as integer) as horse_number,
  Wakuban ::int as gate_number,
  cast(popularity_raw as integer) as popularity,
  nullif(trim(Odds), '')::float/10.0 as odds_tansho,
  cast(result_order_raw as integer) as result_order,
  rank_1c,
  rank_2c,
  rank_3c,
  rank_4c,
  agari3f,
  agari4f,
  case 
    when time_diff_raw < 0 then 0.0
    when time_diff_raw >= 0 then time_diff_raw
    else null
  end as time_diff,
  nullif(time_sec, 0) as time_sec,
  case 
  when running_style_cd = 0 then null
       else running_style_cd
  end as running_style_cd,
  blinker_cd

from src
where
  -- まずは「確定着順がある行」だけを対象にするのが安全
  result_order_raw is not null
  and src.held_date >= '2008-01-01'
  and ijyo_cd is null
  and datakubun in ('1', '2','3','4','5','6','7')
  and src.held_date != '2025-02-10'
