{{ config(
    materialized='view',
    description='1:1 staging model for s_jodds_umaren source data.'
) }}

with source_rows as (
    select
        *,
        concat(
            trim(year),
            lpad(trim(monthday), 4, '0'),
            lpad(trim(jyocd), 2, '0'),
            lpad(trim(kaiji), 2, '0'),
            lpad(trim(nichiji), 2, '0'),
            lpad(trim(racenum), 2, '0')
        )::bigint as race_id,
        regexp_replace(trim(kumi), '[^0-9]', '', 'g') as pair_digits,
        nullif(trim(odds), '')::int / 10.0 as odds_umaren,
        nullif(trim(ninki), '')::int as popularity,
        happyotime::int as happyo_time
    from {{ source('raw', 's_jodds_umaren') }}
    where
        trim(kumi) <> ''
        and trim(odds) not in ('', '----', '****', '------', '******')
),

normalized as (
    select
        *,
        least(substr(pair_digits, 1, 2)::int, substr(pair_digits, 3, 2)::int) as horse_number_1,
        greatest(substr(pair_digits, 1, 2)::int, substr(pair_digits, 3, 2)::int) as horse_number_2
    from source_rows
    where length(pair_digits) >= 4
)

select
    *,
    lpad(horse_number_1::text, 2, '0') || '-' || lpad(horse_number_2::text, 2, '0') as pair_key
from normalized
