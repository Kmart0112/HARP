{{ config(tags=['manual_refresh', 'expensive']) }}

select distinct on (sjt.race_id, sjt.horse_number)
  sjt.*,
  r.hassotime
from {{ ref('stg_n_jodds_tanpuku') }} sjt
left join {{ ref('fct_race') }} r
  using (race_id)
where
  sjt.happyo_time::time <= r.hassotime - interval '10 minutes'
order by
  sjt.race_id,
  sjt.horse_number,
  sjt.happyo_time desc
