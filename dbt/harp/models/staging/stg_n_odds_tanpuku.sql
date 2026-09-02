{{config(
  materialized='incremental',
  unique_key=['race_id','horse_number'],
  tags=['prd']
)}}

select
    concat(
      trim(year),
      lpad(trim(monthday), 4, '0'),
      lpad(trim(jyocd), 2, '0'),
      lpad(trim(kaiji), 2, '0'),
      lpad(trim(nichiji), 2, '0'),
      lpad(trim(racenum), 2, '0')
    )::bigint as race_id,
    umaban::int as horse_number,
    nullif(trim(tanodds),'')::int / 10.0 as odds_tansho,
    nullif(trim(fukuoddslow),'')::int / 10.0 as odds_fukusho_low,
    nullif(trim(fukuoddshigh),'')::int / 10.0 as odds_fukusho_high
from {{ source('raw', 'n_odds_tanpuku') }}
where
    tanodds != '----'
    and tanodds != '****'
    and fukuoddslow != '----'
    and fukuoddshigh != '----'
    {% if is_incremental() %}
    and concat(
      trim(year),
      lpad(trim(monthday), 4, '0'),
      lpad(trim(jyocd), 2, '0'),
      lpad(trim(kaiji), 2, '0'),
      lpad(trim(nichiji), 2, '0'),
      lpad(trim(racenum), 2, '0')
    )::bigint > (select coalesce(max(race_id), 0) from {{ this }})
    {% endif %}
