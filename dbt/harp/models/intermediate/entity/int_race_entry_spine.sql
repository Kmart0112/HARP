{{ config(
  materialized='incremental',
  unique_key=['race_id', 'kettonum'],
  on_schema_change='sync_all_columns',
  tags=['race_week_static']
) }}

with declared as (
  select *
  from {{ ref('fct_race_entry_declared') }}
  {% if is_incremental() %}
    where held_date between
      '{{ var("race_from_date", "1900-01-01") }}'::date
      and '{{ var("race_to_date", "2999-12-31") }}'::date
  {% endif %}
),

results as (
  select
    race_id,
    kettonum,
    result_order
  from {{ ref('fct_race_entry_result') }}
)

select
  d.race_id,
  d.kettonum,
  d.held_date,
  d.horse_number,
  d.gate_number,
  d.ijyo_cd,
  d.is_scratched_or_excluded,
  r.result_order is not null as has_result,
  case
    when d.is_scratched_or_excluded then 'scratched'
    when r.result_order is not null then 'resulted'
    else 'declared'
  end as entry_status,
  (not d.is_scratched_or_excluded) and r.result_order is null as is_prediction_target
from declared d
left join results r
  using (race_id, kettonum)
