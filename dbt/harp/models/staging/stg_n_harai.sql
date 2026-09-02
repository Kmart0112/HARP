{{ config(materialized='table') }}


select
    *,
    nullif(PayTansyoUmaban1, '') ::int as tansyo_umaban1,
    nullif(PayTansyoUmaban2, '') ::int as tansyo_umaban2,
    nullif(PayTansyoPay1, '') ::int as tansyo_pay1,
    nullif(PayTansyoPay2, '') ::int as tansyo_pay2,
    nullif(PayFukusyoUmaban1, '') ::int as fukusyo_umaban1,
    nullif(PayFukusyoUmaban2, '') ::int as fukusyo_umaban2,
    nullif(PayFukusyoUmaban3, '') ::int as fukusyo_umaban3,
    nullif(payfukusyoumaban4, '') ::int as fukusyo_umaban4,
    nullif(payfukusyoumaban5, '') ::int as fukusyo_umaban5,
    nullif(PayFukusyoPay1, '') ::int as fukusyo_pay1,
    nullif(PayFukusyoPay2, '') ::int as fukusyo_pay2,
    nullif(PayFukusyoPay3, '') ::int as fukusyo_pay3,
    nullif(payfukusyopay4, '') ::int as fukusyo_pay4,
    nullif(payfukusyopay5, '') ::int as fukusyo_pay5,
    
    concat(
        year,
        monthday,
        lpad(trim(jyocd), 2, '0'),
        lpad(kaiji::text, 2, '0'),
        lpad(nichiji::text, 2, '0'),
        lpad(racenum::text, 2, '0')
    )::bigint  as race_id
from  {{ source('raw', 'n_harai') }}