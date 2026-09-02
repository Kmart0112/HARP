{{ config(
  materialized='incremental',
  unique_key=['kettonum', 'held_date'],
  tags=['feature']
) }}
{% set pace_ntile_half_life_days = 180 %}

with incremental_bounds as (
  {% if is_incremental() %}
    select
      coalesce(max(held_date), '1900-01-01'::date) as max_held_date,
      (
        coalesce(max(held_date), '1900-01-01'::date)
        - ({{ var('incremental_recalc_days') }} * interval '1 day')
      )::date as recalc_from_date,
      (
        coalesce(max(held_date), '1900-01-01'::date)
        - ({{ var('incremental_recalc_days') }} * interval '1 day')
        - interval '3 years'
      )::date as hist_from_date
    from {{ this }}
  {% else %}
    select
      null::date as max_held_date,
      null::date as recalc_from_date,
      null::date as hist_from_date
  {% endif %}
),

base as (
  select
    race_id,
    kettonum,
    held_date,
    ten3f_ntile,
    is_place,
    pos4_agari_synergy
  from {{ ref('feat_race_entry_base') }}
  where ten3f_ntile is not null
  {% if is_incremental() %}
    and held_date >= (select hist_from_date from incremental_bounds)
  {% endif %}
),

daily_pace_ntile as (
  select
    kettonum,
    held_date,
    ten3f_ntile,
    count(*) as starts_on_day,
    sum(is_place) as places_on_day,
    sum(pos4_agari_synergy) as pos4_agari_synergy_on_day
  from base
  group by
    kettonum,
    held_date,
    ten3f_ntile
),

horse_dates as (
  select distinct
    kettonum,
    held_date
  from base
),

pace_ntile_master as (
  select 1 as ten3f_ntile
  union all
  select 2 as ten3f_ntile
  union all
  select 3 as ten3f_ntile
),

horse_date_ntile_grid as (
  select
    hd.kettonum,
    hd.held_date,
    pnm.ten3f_ntile
  from horse_dates hd
  cross join pace_ntile_master pnm
),

cur_horse_date_ntile_grid as (
  select
    *
  from horse_date_ntile_grid
  {% if is_incremental() %}
    where held_date >= (select recalc_from_date from incremental_bounds)
  {% endif %}
),

pace_ntile_cum as (
  select
    cur.kettonum,
    cur.held_date,
    cur.ten3f_ntile,
    coalesce(sum(hist.starts_on_day), 0) as pace_ntile_past_starts,
    coalesce(sum(hist.places_on_day), 0) as pace_ntile_past_places,
    coalesce(sum(hist.pos4_agari_synergy_on_day), 0) as pace_ntile_past_pos4_agari_synergy,
    coalesce(
      sum(
        hist.starts_on_day
        * power(
            0.5::float,
            (cur.held_date - hist.held_date)::float / {{ pace_ntile_half_life_days }}::float
          )
      ),
      0
    ) as pace_ntile_past_weighted_starts,
    coalesce(
      sum(
        hist.places_on_day
        * power(
            0.5::float,
            (cur.held_date - hist.held_date)::float / {{ pace_ntile_half_life_days }}::float
          )
      ),
      0
    ) as pace_ntile_past_weighted_places,
    coalesce(
      sum(
        hist.pos4_agari_synergy_on_day
        * power(
            0.5::float,
            (cur.held_date - hist.held_date)::float / {{ pace_ntile_half_life_days }}::float
          )
      ),
      0
    ) as pace_ntile_past_weighted_pos4_agari_synergy
  from cur_horse_date_ntile_grid cur
  left join daily_pace_ntile hist
    on cur.kettonum = hist.kettonum
    and cur.ten3f_ntile = hist.ten3f_ntile
    and hist.held_date < cur.held_date
    and hist.held_date >= cur.held_date - interval '3 years'
  group by
    cur.kettonum,
    cur.held_date,
    cur.ten3f_ntile
),

daily_pace_ntile_pivot as (
  select
    kettonum,
    held_date,
    max(case when ten3f_ntile = 1 then pace_ntile_past_starts end) as pace_ntile1_past_starts,
    max(case when ten3f_ntile = 1 then pace_ntile_past_places end) as pace_ntile1_past_places,
    max(case when ten3f_ntile = 1 then pace_ntile_past_pos4_agari_synergy end) as pace_ntile1_past_pos4_agari_synergy,
    max(case when ten3f_ntile = 1 then pace_ntile_past_weighted_starts end) as pace_ntile1_past_weighted_starts,
    max(case when ten3f_ntile = 1 then pace_ntile_past_weighted_places end) as pace_ntile1_past_weighted_places,
    max(case when ten3f_ntile = 1 then pace_ntile_past_weighted_pos4_agari_synergy end) as pace_ntile1_past_weighted_pos4_agari_synergy,

    max(case when ten3f_ntile = 2 then pace_ntile_past_starts end) as pace_ntile2_past_starts,
    max(case when ten3f_ntile = 2 then pace_ntile_past_places end) as pace_ntile2_past_places,
    max(case when ten3f_ntile = 2 then pace_ntile_past_pos4_agari_synergy end) as pace_ntile2_past_pos4_agari_synergy,
    max(case when ten3f_ntile = 2 then pace_ntile_past_weighted_starts end) as pace_ntile2_past_weighted_starts,
    max(case when ten3f_ntile = 2 then pace_ntile_past_weighted_places end) as pace_ntile2_past_weighted_places,
    max(case when ten3f_ntile = 2 then pace_ntile_past_weighted_pos4_agari_synergy end) as pace_ntile2_past_weighted_pos4_agari_synergy,

    max(case when ten3f_ntile = 3 then pace_ntile_past_starts end) as pace_ntile3_past_starts,
    max(case when ten3f_ntile = 3 then pace_ntile_past_places end) as pace_ntile3_past_places,
    max(case when ten3f_ntile = 3 then pace_ntile_past_pos4_agari_synergy end) as pace_ntile3_past_pos4_agari_synergy,
    max(case when ten3f_ntile = 3 then pace_ntile_past_weighted_starts end) as pace_ntile3_past_weighted_starts,
    max(case when ten3f_ntile = 3 then pace_ntile_past_weighted_places end) as pace_ntile3_past_weighted_places,
    max(case when ten3f_ntile = 3 then pace_ntile_past_weighted_pos4_agari_synergy end) as pace_ntile3_past_weighted_pos4_agari_synergy
  from pace_ntile_cum
  group by
    kettonum,
    held_date
)

select
  kettonum,
  held_date,
  pace_ntile1_past_starts,
  pace_ntile1_past_places,
  pace_ntile1_past_pos4_agari_synergy,
  pace_ntile1_past_weighted_starts,
  pace_ntile1_past_weighted_places,
  pace_ntile1_past_weighted_pos4_agari_synergy,
  case
    when pace_ntile1_past_starts > 0 then pace_ntile1_past_pos4_agari_synergy::float / pace_ntile1_past_starts
    else null
  end as pace_ntile1_avg_pos4_agari_synergy,
  case
    when pace_ntile1_past_weighted_starts > 0 then pace_ntile1_past_weighted_pos4_agari_synergy::float / pace_ntile1_past_weighted_starts
    else null
  end as pace_ntile1_weighted_avg_pos4_agari_synergy,
  case
    when pace_ntile1_past_starts > 0 then pace_ntile1_past_places::float / pace_ntile1_past_starts
    else null
  end as pace_ntile1_place_rate,
  case
    when pace_ntile1_past_weighted_starts > 0 then pace_ntile1_past_weighted_places::float / pace_ntile1_past_weighted_starts
    else null
  end as pace_ntile1_weighted_place_rate,

  pace_ntile2_past_starts,
  pace_ntile2_past_places,
  pace_ntile2_past_pos4_agari_synergy,
  pace_ntile2_past_weighted_starts,
  pace_ntile2_past_weighted_places,
  pace_ntile2_past_weighted_pos4_agari_synergy,
  case
    when pace_ntile2_past_starts > 0 then pace_ntile2_past_pos4_agari_synergy::float / pace_ntile2_past_starts
    else null
  end as pace_ntile2_avg_pos4_agari_synergy,
  case
    when pace_ntile2_past_weighted_starts > 0 then pace_ntile2_past_weighted_pos4_agari_synergy::float / pace_ntile2_past_weighted_starts
    else null
  end as pace_ntile2_weighted_avg_pos4_agari_synergy,
  case
    when pace_ntile2_past_starts > 0 then pace_ntile2_past_places::float / pace_ntile2_past_starts
    else null
  end as pace_ntile2_place_rate,
  case
    when pace_ntile2_past_weighted_starts > 0 then pace_ntile2_past_weighted_places::float / pace_ntile2_past_weighted_starts
    else null
  end as pace_ntile2_weighted_place_rate,

  pace_ntile3_past_starts,
  pace_ntile3_past_places,
  pace_ntile3_past_pos4_agari_synergy,
  pace_ntile3_past_weighted_starts,
  pace_ntile3_past_weighted_places,
  pace_ntile3_past_weighted_pos4_agari_synergy,
  case
    when pace_ntile3_past_starts > 0 then pace_ntile3_past_pos4_agari_synergy::float / pace_ntile3_past_starts
    else null
  end as pace_ntile3_avg_pos4_agari_synergy,
  case
    when pace_ntile3_past_weighted_starts > 0 then pace_ntile3_past_weighted_pos4_agari_synergy::float / pace_ntile3_past_weighted_starts
    else null
  end as pace_ntile3_weighted_avg_pos4_agari_synergy,
  case
    when pace_ntile3_past_starts > 0 then pace_ntile3_past_places::float / pace_ntile3_past_starts
    else null
  end as pace_ntile3_place_rate,
  case
    when pace_ntile3_past_weighted_starts > 0 then pace_ntile3_past_weighted_places::float / pace_ntile3_past_weighted_starts
    else null
  end as pace_ntile3_weighted_place_rate,

  case
    when pace_ntile1_past_starts > 0 and pace_ntile3_past_starts > 0 then
      (pace_ntile1_past_places::float / nullif(pace_ntile1_past_starts, 0))
      - (pace_ntile3_past_places::float / nullif(pace_ntile3_past_starts, 0))
    else null
  end as pace_fast_minus_slow_place_rate,
  case
    when pace_ntile1_past_weighted_starts > 0 and pace_ntile3_past_weighted_starts > 0 then
      (pace_ntile1_past_weighted_places::float / nullif(pace_ntile1_past_weighted_starts, 0))
      - (pace_ntile3_past_weighted_places::float / nullif(pace_ntile3_past_weighted_starts, 0))
    else null
  end as pace_fast_minus_slow_weighted_place_rate
from daily_pace_ntile_pivot
