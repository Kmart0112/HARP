{{ config(
    materialized='table',
    tags=['prd'],
    description='Latest published row per race and umaren pair from stg_s_jodds_umaren.'
) }}

select distinct on (race_id, horse_number_1, horse_number_2)
    *
from {{ ref('stg_s_jodds_umaren') }}
order by race_id, horse_number_1, horse_number_2, happyo_time desc nulls last

