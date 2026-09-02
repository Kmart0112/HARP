{{ config(
  materialized='view',
  tags=['race_day_live', 'race_day_odds']
) }}

with latest as (
  select
    race_id,
    horse_number,
    odds_snapshot_type,
    snapshot_at,
    odds_tansho,
    odds_fukusho_low,
    odds_fukusho_high,
    odds_fukusho_avg,
    odds_fukusho_weighted_avg,
    popularity,
    odds_source
  from {{ ref('int_race_day_odds_latest') }}
)

select
  race_id,
  horse_number,
  odds_snapshot_type,
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
