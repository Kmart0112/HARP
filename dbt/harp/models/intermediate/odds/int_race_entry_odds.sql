{{ config(
  materialized='table',
  tags=['prd'],
  indexes=[
    {'columns': ['race_id', 'horse_number']}
  ]
) }}

with odds as (
  select
    race_id,
    horse_number,
    popularity,
    odds_tansho
  from {{ ref('int_s_jodds_latest') }}
  where popularity is not null
),

jodds as (
  select
    race_id,
    horse_number,
    odds_tansho
  from {{ source('published_manual', 'fct_jodds_snapshot') }}
  where popularity is not null
)

select
  coalesce(o.race_id, j.race_id) as race_id,
  coalesce(o.horse_number, j.horse_number) as horse_number,
  o.popularity as odds_popularity,
  o.odds_tansho as odds_tansho,
  j.odds_tansho as j_odds_tansho
from odds o
full outer join jodds j
  using (race_id, horse_number)
