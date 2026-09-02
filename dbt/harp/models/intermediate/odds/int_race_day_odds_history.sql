{{ config(
  materialized='table',
  tags=['race_day_live', 'race_day_odds'],
  indexes=[
    {'columns': ['race_id', 'horse_number', 'snapshot_time_key'], 'unique': True},
    {'columns': ['race_id', 'horse_number']},
    {'columns': ['snapshot_at']}
  ]
) }}

with target_races as (
  select race_id
  from {{ ref('fct_race_basic') }}
  where held_date = {{ target_held_date_expr() }}
),

normalized as (
  select
    race_id,
    horse_number,
    happyo_time as snapshot_time_key,
    happyo_time::text as snapshot_at,
    odds_tansho::double precision as odds_tansho,
    odds_fukusho_low::double precision as odds_fukusho_low,
    odds_fukusho_high::double precision as odds_fukusho_high,
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
    's_jodds_tanpuku'::text as odds_source
  from {{ ref('stg_s_jodds_tanpuku') }}
  where race_id is not null
    and horse_number is not null
    and happyo_time is not null
    and race_id in (select race_id from target_races)
)

select
  race_id,
  horse_number,
  snapshot_time_key,
  snapshot_at,
  odds_tansho,
  odds_fukusho_low,
  odds_fukusho_high,
  odds_fukusho_avg,
  odds_fukusho_weighted_avg,
  popularity,
  odds_source,
  now() as updated_at
from normalized
