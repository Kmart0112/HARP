{{ config(
  materialized='incremental',
  on_schema_change='sync_all_columns',
  unique_key=['race_id', 'kettonum'],
  tags=['mart', 'reporting', 'main']
) }}

with entries as (
  select
    race_id,
    kettonum,
    horse_number,
    horse_name,
    sire_id,
    sire_name,
    jockey_cd,
    trainer_cd,
    breeder_cd,
    age,
    popularity,
    odds_tansho,
    held_date,
    jyo_cd,
    distance_m,
    surface,
    surface_condition,
    surface_condition_cd,
    track_cd
  from {{ ref('int_race_entry_enriched') }}
  {% if is_incremental() %}
    where held_date >= current_date - interval '7 days'
  {% endif %}
),

races as (
  select
    race_id,
    round,
    name as race_name,
    jyo_name,
    surface_name,
    track_cd_label,
    turn_direction,
    course_variant,
    straight_distance_m,
    has_homestretch_slope,
    race_level,
    num_starters
  from {{ ref('fct_race') }}
),

odds as (
  select
    race_id,
    horse_number,
    odds_popularity,
    odds_tansho as latest_odds_tansho,
    j_odds_tansho
  from {{ ref('int_race_entry_odds') }}
)

select
  e.race_id,
  e.kettonum,
  e.horse_number,
  e.horse_name,
  e.sire_id,
  e.sire_name,
  e.jockey_cd,
  e.trainer_cd,
  e.breeder_cd,
  e.age,
  coalesce(o.odds_popularity, e.popularity) as popularity,
  coalesce(o.latest_odds_tansho, e.odds_tansho) as odds_tansho,
  o.j_odds_tansho,
  e.held_date,
  e.jyo_cd,
  r.jyo_name,
  r.round,
  r.race_name,
  e.distance_m,
  e.surface,
  r.surface_name,
  e.surface_condition,
  e.surface_condition_cd,
  e.track_cd,
  r.track_cd_label,
  r.turn_direction,
  r.course_variant,
  r.straight_distance_m,
  r.has_homestretch_slope,
  r.race_level,
  r.num_starters
from entries e
left join races r
  using (race_id)
left join odds o
  on e.race_id = o.race_id
  and e.horse_number = o.horse_number
