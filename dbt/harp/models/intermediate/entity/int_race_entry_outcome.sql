{{ config(
  materialized='incremental',
  unique_key=['race_id', 'kettonum'],
  on_schema_change='sync_all_columns',
  tags=['post_race', 'training']
) }}

select
  race_id,
  kettonum,
  held_date,
  result_order,
  is_win,
  is_place
from {{ ref('fct_race_entry_result') }}
where result_order is not null
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
