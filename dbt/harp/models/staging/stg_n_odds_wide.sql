{{ config(
    materialized='incremental',
    unique_key=['race_id', 'horse_number_1', 'horse_number_2'],
    tags=['prd']
) }}

with source_rows as (
    select
        concat(
            trim(year),
            lpad(trim(monthday), 4, '0'),
            lpad(trim(jyocd), 2, '0'),
            lpad(trim(kaiji), 2, '0'),
            lpad(trim(nichiji), 2, '0'),
            lpad(trim(racenum), 2, '0')
        )::bigint as race_id,
        regexp_replace(trim(kumi), '[^0-9]', '', 'g') as pair_digits,
        nullif(trim(oddslow), '')::int / 10.0 as odds_wide_low,
        nullif(trim(oddshigh), '')::int / 10.0 as odds_wide_high,
        nullif(trim(ninki), '')::int as popularity
    from {{ source('raw', 'n_odds_wide') }}
    where
        trim(kumi) <> ''
        and trim(oddslow) not in ('', '----', '****', '-----', '*****', '------', '******')
        and trim(oddshigh) not in ('', '----', '****', '-----', '*****', '------', '******')
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
),

normalized as (
    select
        race_id,
        least(substr(pair_digits, 1, 2)::int, substr(pair_digits, 3, 2)::int) as horse_number_1,
        greatest(substr(pair_digits, 1, 2)::int, substr(pair_digits, 3, 2)::int) as horse_number_2,
        odds_wide_low,
        odds_wide_high,
        popularity
    from source_rows
    where length(pair_digits) >= 4
)

select
    race_id,
    horse_number_1,
    horse_number_2,
    lpad(horse_number_1::text, 2, '0') || '-' || lpad(horse_number_2::text, 2, '0') as pair_key,
    odds_wide_low,
    odds_wide_high,
    (odds_wide_low + odds_wide_high) / 2.0 as odds_wide_mid,
    popularity
from normalized

