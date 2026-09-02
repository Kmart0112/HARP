{{ config(
  materialized='incremental',
  unique_key=['race_id', 'kettonum'],
  on_schema_change='sync_all_columns',
  tags=['post_race']
) }}

with entries as (
  select *
  from {{ ref('stg_n_uma_race_all') }}
  where has_result
  {% if var('target_held_date', none) is not none %}
    and held_date = '{{ var("target_held_date") }}'::date
  {% elif is_incremental() %}
    and held_date between
      '{{ var("race_from_date", "1900-01-01") }}'::date
      and '{{ var("race_to_date", "2999-12-31") }}'::date
  {% endif %}
),

races as (
  select
    race_id,
    num_starters
  from {{ ref('fct_race') }}
)

select
  e.race_id,
  e.kettonum,
  e.held_date,
  e.dm_rank,
  e.popularity,
  e.odds_tansho,
  e.result_order,
  e.running_style_cd,
  e.rank_1c,
  e.rank_2c,
  e.rank_3c,
  e.rank_4c,
  e.agari3f,
  e.agari4f,
  e.time_diff,
  case
    when e.time_diff is null then null
    else log(e.time_diff + 1)
  end as time_diff_log,
  e.time_sec,
  e.result_order = 1 as is_win,
  case
    when r.num_starters < 8 and e.result_order <= 2 then true
    when r.num_starters >= 8 and e.result_order <= 3 then true
    else false
  end as is_place
from entries e
left join races r
  using (race_id)
