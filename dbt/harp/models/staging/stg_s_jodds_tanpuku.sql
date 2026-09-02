{{ config(
    materialized='view',
    description='1:1 staging model for s_jodds_tanpuku source data.'
) }}

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
    umaban::int as horse_number,
    tanninki::int as popularity,
    nullif(trim(tanodds),'')::int / 10.0 as odds_tansho,
    nullif(trim(fukuoddslow),'')::int / 10.0 as odds_fukusho_low,
    nullif(trim(fukuoddshigh),'')::int / 10.0 as odds_fukusho_high,
    happyotime::int as happyo_time
from {{ source('raw', 's_jodds_tanpuku') }}
where
    tanodds != '----'
    and tanodds != '****'
    and fukuoddslow != '----'
    and fukuoddshigh != '----'
