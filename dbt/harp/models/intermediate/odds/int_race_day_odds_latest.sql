{{ config(
  materialized='table',
  tags=['race_day_live', 'race_day_odds'],
  indexes=[
    {'columns': ['race_id', 'horse_number'], 'unique': True},
    {'columns': ['snapshot_at']}
  ]
) }}

with history as (
  select *
  from {{ ref('int_race_day_odds_history') }}
),

latest as (
  select distinct on (race_id, horse_number)
    race_id,
    horse_number,
    'latest'::text as odds_snapshot_type,
    snapshot_time_key,
    snapshot_at,
    odds_tansho,
    odds_fukusho_low,
    odds_fukusho_high,
    odds_fukusho_avg,
    odds_fukusho_weighted_avg,
    popularity,
    'int_race_day_odds_history'::text as odds_source
  from history
  order by race_id, horse_number, snapshot_time_key desc nulls last
)

select
  race_id,
  horse_number,
  odds_snapshot_type,
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
from latest
