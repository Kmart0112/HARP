{{ config(
  materialized='table',
  tags=['inference', 'race_day_live']
) }}

with features as (
  select *
  from {{ ref('m_race_entry_feature_matrix') }}
  where held_date = {{ target_held_date_expr() }}
    and not is_scratched
),

odds as (
  select *
  from {{ ref('int_race_day_odds_latest') }}
)

select
  f.*,
  coalesce(o.odds_snapshot_type, 'latest') as odds_snapshot_type,
  o.snapshot_at,
  o.popularity,
  o.popularity / nullif(f.num_starters, 0)::float as popularity_ratio,
  o.odds_tansho,
  o.odds_tansho as j_odds_tansho,
  case
    when o.odds_tansho > 0 then ln(o.odds_tansho)
    else null
  end as log_odds_tansho,
  o.odds_fukusho_low,
  o.odds_fukusho_high,
  o.odds_fukusho_avg,
  o.odds_fukusho_weighted_avg,
  coalesce(o.odds_source, 'missing_live_odds') as odds_source
from features f
left join odds o
  on f.race_id = o.race_id
 and f.horse_number = o.horse_number
