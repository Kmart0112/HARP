{{ config(
  materialized='incremental',
  unique_key=['kettonum', 'held_date'],
  tags=['feature']
) }}
{% set overall_half_life_days = 180 %}

with incremental_bounds as (
    {% if is_incremental() %}
        select
            coalesce(max(held_date), '1900-01-01'::date) as max_held_date,
            (
                coalesce(max(held_date), '1900-01-01'::date)
                - ({{ var('incremental_recalc_days') }} * interval '1 day')
            )::date as recalc_from_date
        from {{ this }}
    {% else %}
        select
            null::date as max_held_date,
            null::date as recalc_from_date
    {% endif %}
),

base as (
    select
        race_id,
        kettonum,
        is_place,
        held_date
    from {{ ref('int_race_entry_enriched') }}

),

daily_horse_overall as (
    select
        kettonum,
        held_date,
        count(*) as starts_on_day,
        sum(is_place) as places_on_day
    from base
    group by
        kettonum,
        held_date
),

cur_horse_overall as (
    select
        *
    from daily_horse_overall
    {% if is_incremental() %}
        where held_date >= (select recalc_from_date from incremental_bounds)
    {% endif %}
),

horse_overall_cum as (
    select
        cur.kettonum,
        cur.held_date,
        coalesce(sum(hist.starts_on_day), 0) as past_starts,
        coalesce(sum(hist.places_on_day), 0) as past_places,
        coalesce(
            sum(
                hist.starts_on_day
                * power(
                    0.5::float,
                    (cur.held_date - hist.held_date)::float / {{ overall_half_life_days }}::float
                )
            ),
            0
        ) as past_weighted_starts,
        coalesce(
            sum(
                hist.places_on_day
                * power(
                    0.5::float,
                    (cur.held_date - hist.held_date)::float / {{ overall_half_life_days }}::float
                )
            ),
            0
        ) as past_weighted_places
    from cur_horse_overall cur
    left join daily_horse_overall hist
        on cur.kettonum = hist.kettonum
        and hist.held_date < cur.held_date
    group by
        cur.kettonum,
        cur.held_date
)

select
    kettonum,
    held_date,
    past_starts,
    past_places,
    past_weighted_starts,
    past_weighted_places,
    case
        when past_weighted_starts > 0 then past_weighted_places::float / past_weighted_starts
        else null
    end as past_weighted_place_rate
from horse_overall_cum
