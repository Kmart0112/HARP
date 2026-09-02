{{ config(materialized='table', tags=['prd']) }}

with base as (
    select
        race_id,
        horse_number_1,
        horse_number_2,
        pair_key,
        odds_umaren,
        popularity
    from {{ ref('stg_n_odds_umaren') }}
),

harai_umaren as (
    select
        h.race_id,
        least(substr(regexp_replace(trim(kumi), '[^0-9]', '', 'g'), 1, 2)::int, substr(regexp_replace(trim(kumi), '[^0-9]', '', 'g'), 3, 2)::int) as horse_number_1,
        greatest(substr(regexp_replace(trim(kumi), '[^0-9]', '', 'g'), 1, 2)::int, substr(regexp_replace(trim(kumi), '[^0-9]', '', 'g'), 3, 2)::int) as horse_number_2,
        nullif(trim(pay), '')::int as pay_umaren,
        nullif(trim(ninki), '')::int as result_popularity
    from {{ ref('stg_n_harai') }} h
    cross join lateral (
        values
            (payumarenkumi1, payumarenpay1, payumarenninki1),
            (payumarenkumi2, payumarenpay2, payumarenninki2),
            (payumarenkumi3, payumarenpay3, payumarenninki3)
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
    b.odds_umaren,
    j.happyo_time as odds_snapshot_time_10min,
    j.popularity as odds_popularity_10min,
    j.odds_umaren as odds_umaren_10min,
    coalesce(h.pay_umaren, 0) as pay_umaren,
    h.result_popularity as pay_popularity
from base b
left join harai_umaren h
    on b.race_id = h.race_id
    and b.horse_number_1 = h.horse_number_1
    and b.horse_number_2 = h.horse_number_2
left join {{ source('published_manual', 'fct_jodds_umaren_snapshot') }} j
    on b.race_id = j.race_id
    and b.horse_number_1 = j.horse_number_1
    and b.horse_number_2 = j.horse_number_2
