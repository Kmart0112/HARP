{{ config(
  materialized='incremental',
  unique_key=['kettonum', 'jockey_cd', 'held_date', 'condition_group', 'condition_key1', 'condition_key2'],
  tags=['feature']
) }}
{% set jockey_horse_pair_half_life_days = 180 %}

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
    kettonum,
    jockey_cd,
    held_date,
    course_cluster,
    turn_direction,
    surface,
    is_place,
    pos4_agari_synergy
  from {{ ref('feat_race_entry_base') }}
  where jockey_cd is not null
  {% if is_incremental() %}
    and held_date >= (select hist_from_date from incremental_bounds)
  {% endif %}
),

condition_inputs as (
  select
    kettonum,
    jockey_cd,
    held_date,
    'overall' as condition_group,
    '__ALL__' as condition_key1,
    null::text as condition_key2,
    is_place,
    pos4_agari_synergy
  from base

  union all

  select
    kettonum,
    jockey_cd,
    held_date,
    'course_cluster' as condition_group,
    course_cluster::text as condition_key1,
    null::text as condition_key2,
    is_place,
    pos4_agari_synergy
  from base
  where course_cluster is not null

  union all

  select
    kettonum,
    jockey_cd,
    held_date,
    'turn_direction_surface' as condition_group,
    turn_direction::text as condition_key1,
    surface::text as condition_key2,
    is_place,
    pos4_agari_synergy
  from base
  where turn_direction is not null
    and surface is not null
),

daily_condition as (
  select
    kettonum,
    jockey_cd,
    held_date,
    condition_group,
    condition_key1,
    condition_key2,
    count(*) as starts_on_day,
    sum(is_place) as places_on_day,
    sum(pos4_agari_synergy) as pos4_agari_synergy_on_day
  from condition_inputs
  group by
    kettonum,
    jockey_cd,
    held_date,
    condition_group,
    condition_key1,
    condition_key2
),

cur_condition as (
  select
    *
  from daily_condition
  {% if is_incremental() %}
    where held_date >= (select recalc_from_date from incremental_bounds)
  {% endif %}
),

daily_condition_cum as (
  select
    cur.kettonum,
    cur.jockey_cd,
    cur.held_date,
    cur.condition_group,
    cur.condition_key1,
    cur.condition_key2,
    coalesce(sum(hist.starts_on_day), 0) as past_starts,
    coalesce(sum(hist.places_on_day), 0) as past_places,
    coalesce(sum(hist.pos4_agari_synergy_on_day), 0) as past_pos4_agari_synergy,
    coalesce(
      sum(
        hist.starts_on_day
        * power(
          0.5::float,
          (cur.held_date - hist.held_date)::float / {{ jockey_horse_pair_half_life_days }}::float
        )
      ),
      0
    ) as past_weighted_starts,
    coalesce(
      sum(
        hist.places_on_day
        * power(
          0.5::float,
          (cur.held_date - hist.held_date)::float / {{ jockey_horse_pair_half_life_days }}::float
        )
      ),
      0
    ) as past_weighted_places,
    coalesce(
      sum(
        hist.pos4_agari_synergy_on_day
        * power(
          0.5::float,
          (cur.held_date - hist.held_date)::float / {{ jockey_horse_pair_half_life_days }}::float
        )
      ),
      0
    ) as past_weighted_pos4_agari_synergy
  from cur_condition cur
  left join daily_condition hist
    on cur.kettonum = hist.kettonum
    and cur.jockey_cd = hist.jockey_cd
    and cur.condition_group = hist.condition_group
    and cur.condition_key1 = hist.condition_key1
    and coalesce(cur.condition_key2, '__NULL__') = coalesce(hist.condition_key2, '__NULL__')
    and hist.held_date < cur.held_date
    and hist.held_date >= cur.held_date - interval '3 years'
  group by
    cur.kettonum,
    cur.jockey_cd,
    cur.held_date,
    cur.condition_group,
    cur.condition_key1,
    cur.condition_key2
)

select
  kettonum,
  jockey_cd,
  held_date,
  condition_group,
  condition_key1,
  coalesce(condition_key2, '__NULL__') as condition_key2,
  past_starts,
  past_places,
  past_pos4_agari_synergy,
  past_weighted_starts,
  past_weighted_places,
  past_weighted_pos4_agari_synergy,
  case
    when past_weighted_starts > 0 then
      past_weighted_pos4_agari_synergy::float / past_weighted_starts
    else null
  end as weighted_avg_pos4_agari_synergy
from daily_condition_cum
