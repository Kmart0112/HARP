with history_latest as (
  select distinct on (race_id, horse_number)
    race_id,
    horse_number,
    snapshot_time_key,
    snapshot_at,
    odds_tansho,
    odds_fukusho_low,
    odds_fukusho_high,
    popularity
  from {{ ref('int_race_day_odds_history') }}
  order by race_id, horse_number, snapshot_time_key desc nulls last
),

latest as (
  select
    race_id,
    horse_number,
    snapshot_time_key,
    snapshot_at,
    odds_tansho,
    odds_fukusho_low,
    odds_fukusho_high,
    popularity
  from {{ ref('int_race_day_odds_latest') }}
)

select *
from (
  select * from latest
  except
  select * from history_latest

  union all

  select * from history_latest
  except
  select * from latest
) mismatches
