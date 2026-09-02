{{ config(
    materialized='table',
    tags=['prd'],
    description='Latest published row per race and horse from stg_s_jodds_tanpuku.'
) }}

select distinct on (race_id, horse_number)
    *
from {{ ref('stg_s_jodds_tanpuku') }}
order by race_id, horse_number, happyo_time desc nulls last
