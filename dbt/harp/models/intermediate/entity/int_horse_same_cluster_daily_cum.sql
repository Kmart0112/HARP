{{ config(
  materialized='incremental',
  unique_key=['kettonum', 'held_date', 'course_cluster'],
  tags=['feature']
) }}
{% set same_cluster_half_life_days = 180 %}

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
    is_place,
    time_diff,
    pos4_agari_synergy,
    held_date,
    course_cluster
  from {{ ref('feat_race_entry_base') }}
  where course_cluster is not null
  {% if is_incremental() %}
    and held_date >= (select hist_from_date from incremental_bounds)
  {% endif %}
),

daily_same_cluster as (
  select
    kettonum,
    held_date,
    course_cluster,
    count(*) as starts_on_day,
    sum(is_place) as places_on_day,
    sum(time_diff) as time_diffs_on_day,
    sum(pos4_agari_synergy) as pos4_agari_synergy_on_day
  from base
  group by
    kettonum,
    held_date,
    course_cluster
),

cur_same_cluster as (
  select
    *
  from daily_same_cluster
  {% if is_incremental() %}
    where held_date >= (select recalc_from_date from incremental_bounds)
  {% endif %}
),

daily_same_cluster_cum as (
  select
    cur.kettonum,
    cur.held_date,
    cur.course_cluster,
    sum(hist.starts_on_day) as same_cluster_past_starts,
    sum(hist.places_on_day) as same_cluster_past_places,
    sum(hist.time_diffs_on_day) as same_cluster_past_time_diffs,
    sum(hist.pos4_agari_synergy_on_day) as same_cluster_past_pos4_agari_synergy,
    sum(
      hist.starts_on_day
      * power(
          0.5::float,
          (cur.held_date - hist.held_date)::float / {{ same_cluster_half_life_days }}::float
        )
    ) as same_cluster_past_weighted_starts,
    sum(
      hist.places_on_day
      * power(
          0.5::float,
          (cur.held_date - hist.held_date)::float / {{ same_cluster_half_life_days }}::float
        )
    ) as same_cluster_past_weighted_places,
    sum(
      hist.time_diffs_on_day
      * power(
          0.5::float,
          (cur.held_date - hist.held_date)::float / {{ same_cluster_half_life_days }}::float
        )
    ) as same_cluster_past_weighted_time_diffs,
    sum(
      hist.pos4_agari_synergy_on_day
      * power(
          0.5::float,
          (cur.held_date - hist.held_date)::float / {{ same_cluster_half_life_days }}::float
        )
    ) as same_cluster_past_weighted_pos4_agari_synergy
  from cur_same_cluster cur
  left join daily_same_cluster hist
    on cur.kettonum = hist.kettonum
    and cur.course_cluster = hist.course_cluster
    and hist.held_date < cur.held_date
    and hist.held_date >= cur.held_date - interval '3 years'
  group by
    cur.kettonum,
    cur.held_date,
    cur.course_cluster
)

select
  kettonum,
  held_date,
  course_cluster,
  coalesce(same_cluster_past_starts, 0) as same_cluster_past_starts,
  same_cluster_past_places,
  same_cluster_past_time_diffs,
  same_cluster_past_pos4_agari_synergy,
  same_cluster_past_weighted_starts,
  same_cluster_past_weighted_places,
  same_cluster_past_weighted_time_diffs,
  same_cluster_past_weighted_pos4_agari_synergy,
  case
    when same_cluster_past_weighted_starts > 0 then
      same_cluster_past_weighted_time_diffs::float / same_cluster_past_weighted_starts
    else null
  end as same_cluster_avg_time_diffs,
  case
    when same_cluster_past_weighted_starts > 0 then
      same_cluster_past_weighted_pos4_agari_synergy::float / same_cluster_past_weighted_starts
    else null
  end as same_cluster_avg_pos4_agari_synergy,
  case
    when same_cluster_past_weighted_starts is null or same_cluster_past_weighted_starts = 0 then null
    else same_cluster_past_weighted_places::float / nullif(same_cluster_past_weighted_starts, 0)
  end as same_cluster_place_rate

from daily_same_cluster_cum
