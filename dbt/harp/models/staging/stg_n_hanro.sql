{{ config(
    materialized='incremental',
    unique_key=['kettonum','chokyo_date','chokyo_time','tozai_cd']
) }}

with src as (
    select
        to_date(makedate, 'YYYYMMDD') as make_date,
        tresenkubun::int as tozai_cd,
        to_date(chokyodate, 'YYYYMMDD') as chokyo_date,
        chokyotime::int as chokyo_time,
        kettonum::bigint as kettonum,
        nullif(nullif(trim(harontime4), ''), '0000')::int / 10.0 as haron_time_4,
        nullif(nullif(trim(laptime4), ''), '000')::int / 10.0 as lap_time_4,
        nullif(nullif(trim(harontime3), ''), '0000')::int / 10.0 as haron_time_3,
        nullif(nullif(trim(laptime3), ''), '000')::int / 10.0 as lap_time_3,
        nullif(nullif(trim(harontime2), ''), '0000')::int / 10.0 as haron_time_2,
        nullif(nullif(trim(laptime2), ''), '000')::int / 10.0 as lap_time_2,
        nullif(nullif(trim(laptime1), ''), '000')::int / 10.0 as lap_time_1
    from {{ source('raw', 'n_hanro') }}
)

select *
from src
{% if is_incremental() %}
where chokyo_date >= (select max(chokyo_date) from {{ this }}) - interval '7 day'
{% endif %}
