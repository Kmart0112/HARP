{{ config(materialized='table', tags=['feature'], enabled=false) }}
{% set same_surface_dist_pm200_half_life_days = 180 %}

with base as (
  select
    race_id,
    kettonum,
    is_place,
    pos4_agari_synergy,
    held_date,
    surface,
    distance_m
  from {{ ref('feat_race_entry_base') }}
  where surface is not null
    and distance_m is not null
),

daily_surface_distance as (
  select
    kettonum,
    held_date,
    surface,
    distance_m,
    count(*) as starts_on_day,
    sum(is_place) as places_on_day,
    sum(pos4_agari_synergy) as pos4_agari_synergy_on_day
  from base
  group by
    kettonum,
    held_date,
    surface,
    distance_m
),

daily_surface_distance_pm200_cum as (
  select
    cur.kettonum,
    cur.held_date,
    cur.surface,
    cur.distance_m,
    coalesce(sum(hist.starts_on_day), 0) as same_surface_dist_pm200_past_starts,
    coalesce(sum(hist.places_on_day), 0) as same_surface_dist_pm200_past_places,
    coalesce(sum(hist.pos4_agari_synergy_on_day), 0) as same_surface_dist_pm200_past_pos4_agari_synergy,
    coalesce(
      sum(
        hist.starts_on_day
        * power(
            0.5::float,
            (cur.held_date - hist.held_date)::float / {{ same_surface_dist_pm200_half_life_days }}::float
          )
      ),
      0
    ) as same_surface_dist_pm200_past_weighted_starts,
    coalesce(
      sum(
        hist.places_on_day
        * power(
            0.5::float,
            (cur.held_date - hist.held_date)::float / {{ same_surface_dist_pm200_half_life_days }}::float
          )
      ),
      0
    ) as same_surface_dist_pm200_past_weighted_places,
    coalesce(
      sum(
        hist.pos4_agari_synergy_on_day
        * power(
            0.5::float,
            (cur.held_date - hist.held_date)::float / {{ same_surface_dist_pm200_half_life_days }}::float
          )
      ),
      0
    ) as same_surface_dist_pm200_past_weighted_pos4_agari_synergy
  from daily_surface_distance cur
  left join daily_surface_distance hist
    on cur.kettonum = hist.kettonum
    and cur.surface = hist.surface
    and hist.distance_m between cur.distance_m - 200 and cur.distance_m + 200
    and hist.held_date < cur.held_date
    and hist.held_date >= cur.held_date - interval '3 years'
  group by
    cur.kettonum,
    cur.held_date,
    cur.surface,
    cur.distance_m
)

select
  kettonum,
  held_date,
  surface,
  distance_m,
  same_surface_dist_pm200_past_starts,
  same_surface_dist_pm200_past_places,
  same_surface_dist_pm200_past_pos4_agari_synergy,
  same_surface_dist_pm200_past_weighted_starts,
  same_surface_dist_pm200_past_weighted_places,
  same_surface_dist_pm200_past_weighted_pos4_agari_synergy,
  case
    when same_surface_dist_pm200_past_starts > 0 then
      same_surface_dist_pm200_past_pos4_agari_synergy::float / same_surface_dist_pm200_past_starts
    else null
  end as same_surface_dist_pm200_avg_pos4_agari_synergy,
  case
    when same_surface_dist_pm200_past_weighted_starts > 0 then
      same_surface_dist_pm200_past_weighted_pos4_agari_synergy::float / same_surface_dist_pm200_past_weighted_starts
    else null
  end as same_surface_dist_pm200_weighted_avg_pos4_agari_synergy,
  case
    when same_surface_dist_pm200_past_starts = 0 then null
    else same_surface_dist_pm200_past_places::float / nullif(same_surface_dist_pm200_past_starts, 0)
  end as same_surface_dist_pm200_place_rate,
  case
    when same_surface_dist_pm200_past_weighted_starts = 0 then null
    else same_surface_dist_pm200_past_weighted_places::float / nullif(same_surface_dist_pm200_past_weighted_starts, 0)
  end as same_surface_dist_pm200_weighted_place_rate

from daily_surface_distance_pm200_cum
