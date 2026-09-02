-- depends_on: {{ ref('fct_race_basic') }}

{{ config(
  materialized='incremental',
  unique_key=['race_id', 'horse_number', 'odds_snapshot_type'],
  on_schema_change='sync_all_columns',
  tags=['training', 'odds_snapshot'],
  indexes=[
    {'columns': ['race_id', 'horse_number', 'odds_snapshot_type'], 'unique': True}
  ]
) }}

with target_races as (
  select race_id
  from {{ ref('fct_race_basic') }}
  where 1 = 1
  {% if var('target_held_date', none) is not none %}
    and held_date = '{{ var("target_held_date") }}'::date
  {% endif %}
  {% if var('race_from_date', none) is not none %}
    and held_date >= '{{ var("race_from_date") }}'::date
  {% endif %}
  {% if var('race_to_date', none) is not none %}
    and held_date <= '{{ var("race_to_date") }}'::date
  {% endif %}
),

pre10m as (
  select
    race_id,
    horse_number,
    'pre10m'::text as odds_snapshot_type,
    happyo_time::text as snapshot_at,
    odds_tansho::double precision as odds_tansho,
    odds_fukusho_low::double precision as odds_fukusho_low,
    odds_fukusho_high::double precision as odds_fukusho_high,
    popularity,
    'published_manual.fct_jodds_snapshot'::text as odds_source
  from {{ source('published_manual', 'fct_jodds_snapshot') }}
  where race_id is not null
  {% if var('target_held_date', none) is not none
      or var('race_from_date', none) is not none
      or var('race_to_date', none) is not none %}
    and race_id in (select race_id from target_races)
  {% endif %}
)

select
  race_id,
  horse_number,
  odds_snapshot_type,
  snapshot_at,
  odds_tansho,
  odds_fukusho_low,
  odds_fukusho_high,
  case
    when odds_fukusho_low is not null and odds_fukusho_high is not null
      then (odds_fukusho_low + odds_fukusho_high) / 2.0
    else null
  end::double precision as odds_fukusho_avg,
  case
    when odds_fukusho_low is not null and odds_fukusho_high is not null
      then odds_fukusho_low * 0.7 + odds_fukusho_high * 0.3
    else null
  end::double precision as odds_fukusho_weighted_avg,
  popularity,
  odds_source,
  now() as updated_at
from pre10m
