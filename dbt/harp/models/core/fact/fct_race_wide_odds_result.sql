{{ config(materialized='table', tags=['prd']) }}

with base as (
    select
        race_id,
        horse_number_1,
        horse_number_2,
        pair_key,
        odds_wide_low,
        odds_wide_high,
        odds_wide_mid,
        popularity
    from {{ ref('stg_n_odds_wide') }}
),

harai_wide as (
    select
        h.race_id,
        least(substr(regexp_replace(trim(kumi), '[^0-9]', '', 'g'), 1, 2)::int, substr(regexp_replace(trim(kumi), '[^0-9]', '', 'g'), 3, 2)::int) as horse_number_1,
        greatest(substr(regexp_replace(trim(kumi), '[^0-9]', '', 'g'), 1, 2)::int, substr(regexp_replace(trim(kumi), '[^0-9]', '', 'g'), 3, 2)::int) as horse_number_2,
        nullif(trim(pay), '')::int as pay_wide,
        nullif(trim(ninki), '')::int as result_popularity
    from {{ ref('stg_n_harai') }} h
    cross join lateral (
        values
            (paywidekumi1, paywidepay1, paywideninki1),
            (paywidekumi2, paywidepay2, paywideninki2),
            (paywidekumi3, paywidepay3, paywideninki3),
            (paywidekumi4, paywidepay4, paywideninki4),
            (paywidekumi5, paywidepay5, paywideninki5),
            (paywidekumi6, paywidepay6, paywideninki6),
            (paywidekumi7, paywidepay7, paywideninki7)
    ) as payout(kumi, pay, ninki)
    where
        trim(coalesce(kumi, '')) <> ''
        and trim(coalesce(pay, '')) <> ''
        and length(regexp_replace(trim(kumi), '[^0-9]', '', 'g')) >= 4
)

select
    b.race_id,
    b.horse_number_1,
    b.horse_number_2,
    b.pair_key,
    b.popularity as odds_popularity,
    b.odds_wide_low,
    b.odds_wide_high,
    b.odds_wide_mid,
    cast(null as time) as odds_snapshot_time_10min,
    cast(null as integer) as odds_popularity_10min,
    cast(null as numeric) as odds_wide_low_10min,
    cast(null as numeric) as odds_wide_high_10min,
    cast(null as numeric) as odds_wide_mid_10min,
    coalesce(h.pay_wide, 0) as pay_wide,
    h.result_popularity as pay_popularity
from base b
left join harai_wide h
    on b.race_id = h.race_id
    and b.horse_number_1 = h.horse_number_1
    and b.horse_number_2 = h.horse_number_2

