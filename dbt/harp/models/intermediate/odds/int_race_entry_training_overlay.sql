{{ config(
  materialized='incremental',
  unique_key=['race_id', 'kettonum', 'odds_snapshot_type'],
  on_schema_change='sync_all_columns',
  tags=['training'],
  indexes=[
    {'columns': ['race_id', 'kettonum', 'odds_snapshot_type'], 'unique': True}
  ]
) }}

with spine as (
  select *
  from {{ ref('int_race_entry_spine') }}
  {% if var('target_held_date', none) is not none %}
    where held_date = '{{ var("target_held_date") }}'::date
  {% elif var('race_from_date', none) is not none or var('race_to_date', none) is not none %}
    where 1 = 1
    {% if var('race_from_date', none) is not none %}
      and held_date >= '{{ var("race_from_date") }}'::date
    {% endif %}
    {% if var('race_to_date', none) is not none %}
      and held_date <= '{{ var("race_to_date") }}'::date
    {% endif %}
  {% endif %}
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
)

select
  s.race_id,
  s.kettonum,
  o.odds_snapshot_type,
  o.snapshot_at,
  s.horse_number,
  o.odds_tansho,
  o.odds_fukusho_low,
  o.odds_fukusho_high,
  o.odds_fukusho_avg,
  o.odds_fukusho_weighted_avg,
  coalesce(o.popularity, d.popularity) as popularity,
  d.h_weight,
  d.weight_change,
  rb.base_weather_cd as weather_cd,
  rb.base_surface_condition_cd as surface_condition_cd,
  rb.planned_num_starters as live_num_starters,
  d.ijyo_cd,
  d.ijyo_cd is not null as is_scratched,
  o.odds_source,
  now() as updated_at
from spine s
inner join odds o
  on s.race_id = o.race_id
 and s.horse_number = o.horse_number
left join declared d
  on s.race_id = d.race_id
 and s.kettonum = d.kettonum
left join race_basic rb
  on s.race_id = rb.race_id
