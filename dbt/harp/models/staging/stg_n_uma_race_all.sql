{{ config(
  materialized='view',
  tags=['race_week_static']
) }}

with src as (
  select
    *,
    concat(
      trim(year),
      lpad(trim(monthday), 4, '0'),
      lpad(trim(jyocd), 2, '0'),
      lpad(trim(kaiji), 2, '0'),
      lpad(trim(nichiji), 2, '0'),
      lpad(trim(racenum), 2, '0')
    )::bigint as race_id,
    to_date(year || monthday, 'YYYYMMDD') as held_date,
    nullif(trim(sexcd), '0')::int as sex_cd,
    nullif(nullif(trim(dMjyuni), ''), '0')::int as dm_rank,
    nullif(trim(barei), '')::int as age,
    nullif(trim(ijyocd), '0') as ijyo_cd,
    nullif(nullif(trim(bataijyu), ''), '0')::int as h_weight,
    nullif(trim(futan), '')::int / 10.0 as kinryo,
    nullif(trim(umaban), '') as horse_number_raw,
    nullif(nullif(trim(ninki), ''), '0') as popularity_raw,
    nullif(nullif(trim(kakuteijyuni), ''), '0') as result_order_raw,
    nullif(nullif(trim(jyuni1c), ''), '0')::int as rank_1c,
    nullif(nullif(trim(jyuni2c), ''), '0')::int as rank_2c,
    nullif(nullif(trim(jyuni3c), ''), '0')::int as rank_3c,
    nullif(nullif(trim(jyuni4c), ''), '0')::int as rank_4c,
    nullif(nullif(trim(harontimel3), ''), '000')::int / 10.0 as agari3f,
    nullif(nullif(trim(harontimel4), ''), '000')::int / 10.0 as agari4f,
    case
      when nullif(trim(timediff), '') is null then null
      when trim(timediff) = '999' then null
      else trim(timediff)::int / 10.0
    end as time_diff_raw,
    case
      when nullif(trim("time"), '') is null then null
      else (
        substring("time" from 1 for 1)::int * 60
        + substring("time" from 2 for 2)::int
        + substring("time" from 4 for 1)::int / 10.0
      )
    end as time_sec_raw,
    nullif(nullif(trim(kyakusitukubun), ''), '0')::int as running_style_cd,
    nullif(trim(blinker), '')::int as blinker_cd
  from {{ source('raw', 'n_uma_race') }}
),

typed as (
  select
    race_id,
    held_date,
    datakubun,
    kettonum::bigint as kettonum,
    bamei as horse_name,
    age,
    h_weight,
    case
      when nullif(trim(zogensa), '') is null then null
      when trim(zogensa) = '000' then 0
      when zogenfugo = '+' then trim(zogensa)::int
      when zogenfugo = '-' then 0 - trim(zogensa)::int
      else null
    end as weight_change,
    dm_rank,
    sex_cd,
    kinryo,
    nullif(trim(tozaicd), '')::int as tozai_cd,
    nullif(trim(kisyucode), '')::int as jockey_cd,
    case
      when kisyuryakusyo = '武豊' then 1
      when kisyuryakusyo = 'ルメール' then 2
      when kisyuryakusyo = '川田将雅' then 3
      when kisyuryakusyo = '戸崎圭太' then 4
      when kisyuryakusyo = '丹内祐次' then 5
      when kisyuryakusyo = '北村友一' then 6
      when kisyuryakusyo = '横山武史' then 7
      when kisyuryakusyo = '岩田望来' then 8
      when kisyuryakusyo = '津村明秀' then 9
      when kisyuryakusyo = '松山弘平' then 10
      when kisyuryakusyo = '三浦皇成' then 11
      when kisyuryakusyo = '池添謙一' then 12
      else 0
    end as jockey_cat,
    nullif(trim(chokyosicode), '')::int as trainer_cd,
    horse_number_raw::int as horse_number,
    nullif(trim(wakuban), '')::int as gate_number,
    popularity_raw::int as popularity,
    case
      when trim(odds) in ('', '0000', '----', '****') then null
      else trim(odds)::float / 10.0
    end as odds_tansho,
    result_order_raw::int as result_order,
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
    nullif(time_sec_raw, 0) as time_sec,
    running_style_cd,
    blinker_cd,
    ijyo_cd,
    result_order_raw is not null as has_result
  from src
)

select *
from typed
where
  held_date >= '2008-01-01'
  and datakubun in ('1', '2', '3', '4', '5', '6', '7')
  and held_date != '2025-02-10'
