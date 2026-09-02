{{ config(
  materialized='incremental',
  unique_key=['race_id', 'kettonum', 'odds_snapshot_type'],
  on_schema_change='sync_all_columns',
  tags=['race_day_live'],
  indexes=[
    {'columns': ['race_id', 'kettonum', 'odds_snapshot_type'], 'unique': True}
  ]
) }}

with spine as (
  select *
  from {{ ref('int_race_entry_spine') }}
  where held_date = {{ target_held_date_expr() }}
),

declared as (
  select
    race_id,
    kettonum,
    h_weight,
    weight_change,
    popularity,
    ijyo_cd
  from {{ ref('fct_race_entry_declared') }}
),

s_uma_ranked as (
  select
    race_id,
    kettonum::bigint as kettonum,
    h_weight,
    weight_change,
    popularity,
    ijyo_cd,
    row_number() over (
      partition by race_id, kettonum
      order by datakubun desc nulls last
    ) as rn
  from {{ ref('stg_s_uma_race') }}
),

s_uma as (
  select
    race_id,
    kettonum,
    h_weight,
    weight_change,
    popularity,
    ijyo_cd
  from s_uma_ranked
  where rn = 1
),

race_basic as (
  select
    race_id,
    base_weather_cd,
    base_surface_condition_cd,
    planned_num_starters
  from {{ ref('fct_race_basic') }}
),

odds as (
  select *
  from {{ ref('int_race_entry_live_odds') }}
  where race_id in (
    select race_id
    from {{ ref('fct_race_basic') }}
    where held_date = {{ target_held_date_expr() }}
  )
)

select
  s.race_id,
  s.kettonum,
  coalesce(o.odds_snapshot_type, 'latest') as odds_snapshot_type,
  coalesce(o.snapshot_at, now()::text) as snapshot_at,
  s.horse_number,
  o.odds_tansho,
  o.odds_fukusho_low,
  o.odds_fukusho_high,
  o.odds_fukusho_avg,
  o.odds_fukusho_weighted_avg,
  coalesce(o.popularity, su.popularity, d.popularity) as popularity,
  coalesce(su.h_weight, d.h_weight) as h_weight,
  coalesce(su.weight_change, d.weight_change) as weight_change,
  rb.base_weather_cd as weather_cd,
  rb.base_surface_condition_cd as surface_condition_cd,
  rb.planned_num_starters as live_num_starters,
  coalesce(su.ijyo_cd, d.ijyo_cd) as ijyo_cd,
  coalesce(su.ijyo_cd, d.ijyo_cd) is not null as is_scratched,
  coalesce(o.odds_source, 'missing_live_odds') as odds_source,
  now() as updated_at
from spine s
left join odds o
  on s.race_id = o.race_id
 and s.horse_number = o.horse_number
left join declared d
  on s.race_id = d.race_id
 and s.kettonum = d.kettonum
left join s_uma su
  on s.race_id = su.race_id
 and s.kettonum = su.kettonum
left join race_basic rb
  on s.race_id = rb.race_id
