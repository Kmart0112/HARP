{{ config(
    materialized='table',
    description='Latest published row per race and wide pair from stg_s_odds_wide.'
) }}

select distinct on (race_id, horse_number_1, horse_number_2)
    *
from {{ ref('stg_s_odds_wide') }}
order by race_id, horse_number_1, horse_number_2
