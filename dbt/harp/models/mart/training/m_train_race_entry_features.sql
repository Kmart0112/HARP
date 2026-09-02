{{ config(
  materialized='incremental',
  unique_key=['race_id', 'kettonum', 'odds_snapshot_type'],
  on_schema_change='sync_all_columns',
  tags=['mart', 'training', 'training_features'],
  indexes=[
    {'columns': ['race_id', 'kettonum', 'odds_snapshot_type'], 'unique': True},
    {'columns': ['held_date', 'odds_snapshot_type']}
  ]
) }}

with features as (
  select *
  from {{ ref('m_race_entry_feature_matrix') }}
  where not is_scratched
  {% if var('target_held_date', none) is not none %}
    and held_date = '{{ var("target_held_date") }}'::date
  {% elif var('race_from_date', none) is not none %}
    and held_date >= '{{ var("race_from_date") }}'::date
  {% elif is_incremental() %}
    and held_date >= current_date - interval '7 days'
  {% endif %}
  {% if var('race_to_date', none) is not none %}
    and held_date <= '{{ var("race_to_date") }}'::date
  {% endif %}
),

odds as (
  select *
  from {{ ref('int_race_entry_odds_snapshot') }}
  where odds_snapshot_type = 'pre10m'
  {% if var('target_held_date', none) is not none %}
    and race_id in (
      select race_id
      from {{ ref('fct_race_basic') }}
      where held_date = '{{ var("target_held_date") }}'::date
    )
  {% elif var('race_from_date', none) is not none or var('race_to_date', none) is not none %}
    and race_id in (
      select race_id
      from {{ ref('fct_race_basic') }}
      where 1 = 1
      {% if var('race_from_date', none) is not none %}
        and held_date >= '{{ var("race_from_date") }}'::date
      {% endif %}
      {% if var('race_to_date', none) is not none %}
        and held_date <= '{{ var("race_to_date") }}'::date
      {% endif %}
    )
  {% endif %}
),

outcome as (
  select *
  from {{ ref('int_race_entry_outcome') }}
)

select
  f.*,
  o.odds_snapshot_type,
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
  o.odds_source,
  oc.result_order,
  oc.is_win,
  oc.is_place
from features f
inner join odds o
  on f.race_id = o.race_id
 and f.horse_number = o.horse_number
inner join outcome oc
  on f.race_id = oc.race_id
 and f.kettonum = oc.kettonum
