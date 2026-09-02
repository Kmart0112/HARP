{{ config(
    materialized='view',
    description='Staging table for n_jodds_umaren source data.'
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
        substring(happyotime from 5 for 4)::time as happyo_time,
        regexp_replace(trim(kumi), '[^0-9]', '', 'g') as pair_digits,
        nullif(trim(odds), '')::int / 10.0 as odds_umaren,
        nullif(trim(ninki), '')::int as popularity
    from {{ source('raw', 'n_jodds_umaren') }}
    where
        trim(kumi) <> ''
        and trim(odds) not in ('', '----', '****', '------', '******')
),

normalized as (
    select
        race_id,
        happyo_time,
        least(substr(pair_digits, 1, 2)::int, substr(pair_digits, 3, 2)::int) as horse_number_1,
        greatest(substr(pair_digits, 1, 2)::int, substr(pair_digits, 3, 2)::int) as horse_number_2,
        odds_umaren,
        popularity
    from source_rows
    where length(pair_digits) >= 4
)

select
    race_id,
    happyo_time,
    horse_number_1,
    horse_number_2,
    lpad(horse_number_1::text, 2, '0') || '-' || lpad(horse_number_2::text, 2, '0') as pair_key,
    odds_umaren,
    popularity
from normalized
