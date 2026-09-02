{{ config(
  materialized='table',
  tags=['odds_validation'],
  indexes=[
    {'columns': ['race_id', 'horse_number'], 'unique': True}
  ]
) }}

with final_odds as (
  select distinct on (race_id, horse_number)
    race_id,
    horse_number,
    odds_tansho::double precision as odds_tansho,
    odds_fukusho_low::double precision as odds_fukusho_low,
    odds_fukusho_high::double precision as odds_fukusho_high
  from {{ ref('stg_n_odds_tanpuku') }}
  where race_id is not null
    and horse_number is not null
  order by race_id, horse_number
)

select
  race_id,
  horse_number,
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
  'n_odds_tanpuku'::text as odds_source,
  now() as updated_at
from final_odds
