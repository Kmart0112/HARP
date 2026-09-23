{% set feature_input_mode = var('feature_input_mode', var('feature_snapshot_mode', 'training')) %}
{% if feature_input_mode not in ['training', 'latest', 'all'] %}
  {{ exceptions.raise_compiler_error('feature_input_mode must be one of: training, latest, all') }}
{% endif %}

{{ config(
  materialized='table',
  tags=['nn_inputs', 'nn_current'],
  indexes=[{'columns': ['race_id', 'kettonum'], 'unique': True}]
) }}

with targets as (
  select *
  from {{ ref('feat_race_entry_pre_race') }} p
  where coalesce(p.ijyo_cd, '0') not in ('1', '2', '3')
    and p.horse_number > 0
    and (
      {% if feature_input_mode == 'latest' %}
        p.held_date = {{ target_held_date_expr() }}
      {% else %}
        (
          1 = 1
          {% if var('target_held_date', none) is not none %}
            and p.held_date = '{{ var("target_held_date") }}'::date
          {% else %}
            {% if var('race_from_date', none) is not none %}
              and p.held_date >= '{{ var("race_from_date") }}'::date
            {% endif %}
            {% if var('race_to_date', none) is not none %}
              and p.held_date <= '{{ var("race_to_date") }}'::date
            {% endif %}
          {% endif %}
        )
        {% if feature_input_mode == 'all' %}
          or p.held_date = {{ target_held_date_expr() }}
        {% endif %}
      {% endif %}
    )
)

select
  p.race_id,
  p.kettonum,
  p.held_date,
  coalesce(h.run_no, 0)::bigint as history_end_no,
  h.race_id as last_history_race_id,
  h.held_date as last_history_held_date,
  p.held_date - h.held_date as days_since_last_run,
  count(*) over (partition by p.race_id) as active_entrant_count,
  {{ nn_select_pre_race_features('p') }},
  {{ nn_select_stats_metadata('p') }}
from targets p
left join lateral (
  select r.run_no, r.race_id, r.held_date
  from {{ ref('int_race_entry_run_record') }} r
  where r.kettonum = p.kettonum
    -- Day-level contract: exclude ALL same-day runs, including the target.
    and r.held_date < p.held_date
  order by r.held_date desc, r.run_no desc
  limit 1
) h on true
