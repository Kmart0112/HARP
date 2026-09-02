{{ config(tags=['manual_refresh', 'expensive']) }}

select distinct on (sju.race_id, sju.horse_number_1, sju.horse_number_2)
    sju.*,
    r.hassotime
from {{ ref('stg_n_jodds_umaren') }} sju
left join {{ ref('fct_race') }} r
    using (race_id)
where
    sju.happyo_time::time <= r.hassotime - interval '10 minutes'
order by
    sju.race_id,
    sju.horse_number_1,
    sju.horse_number_2,
    sju.happyo_time desc

