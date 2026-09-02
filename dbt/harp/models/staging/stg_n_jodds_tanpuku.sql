{{ config(
    materialized = 'view',
    description = 'Staging table for n_jodds_tanpuku source data',
) }}
select
    concat(
      trim(year),
      lpad(trim(monthday), 4, '0'),
      lpad(trim(jyocd), 2, '0'),
      lpad(trim(kaiji), 2, '0'),
      lpad(trim(nichiji), 2, '0'),
      lpad(trim(racenum), 2, '0')
        )::bigint as race_id,
    substring(happyotime from 5 for 4) ::time as happyo_time,
    umaban ::int as horse_number,
    tanodds ::float/10.0 as odds_tansho,
    fukuoddslow ::float/10.0 as odds_fukusho_low,
    fukuoddshigh ::float/10.0 as odds_fukusho_high,
    tanninki ::int as popularity
from {{ source('raw', 'n_jodds_tanpuku') }}
where
    tanodds != '----' and
    tanodds != '****' and
    fukuoddslow != '----' and
    fukuoddshigh != '----'



