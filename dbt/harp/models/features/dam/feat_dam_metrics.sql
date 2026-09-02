{{ config(
  materialized='incremental',
  unique_key=['race_id', 'kettonum'],
  tags=['feature'],
  indexes=[
    {'columns': ['race_id', 'kettonum']}
  ]
) }}

with incremental_bounds as (
  {% if is_incremental() %}
    select
      coalesce(max(frh.held_date), '1900-01-01'::date) as max_held_date,
      (
        coalesce(max(frh.held_date), '1900-01-01'::date)
        - ({{ var('incremental_recalc_days') }} * interval '1 day')
      )::date as recalc_from_date
    from {{ this }} t
    left join {{ ref('feat_race_entry_base') }} frh
      on t.race_id = frh.race_id
      and t.kettonum = frh.kettonum
  {% else %}
    select
      null::date as max_held_date,
      null::date as recalc_from_date
  {% endif %}
),

long as (
  select
    race_id,
    kettonum,
    dam_id,
    held_year_month,
    course_cluster
  from {{ ref('feat_race_entry_base') }}
  {% if is_incremental() %}
    where held_date >= (select recalc_from_date from incremental_bounds)
  {% endif %}
),

dam_yearly_overall as (
  select
    *
  from {{ ref('feat_dam_yearly_overall') }}
),

dam_yearly_cluster as (
  select
    *
  from {{ ref('feat_dam_yearly_cluster') }}
)

select
  l.race_id,
  l.kettonum,
  coalesce(dy.dam_starts_5y, 0) as dam_starts_5y,
  dy.dam_avg_place_rate,
  dy.dam_avg_place_rate_smooth,
  dy.dam_avg_pos4_agari_synergy,
  dy.dam_avg_time_diff,
  coalesce(dc.same_cluster_dam_starts_5y, 0) as same_cluster_dam_past_starts,
  dc.same_cluster_dam_avg_place_rate,
  dc.same_cluster_dam_avg_place_rate_smooth,
  dc.same_cluster_dam_avg_pos4_agari_synergy
from long l
left join dam_yearly_overall dy
  on l.dam_id = dy.dam_id
  and l.held_year_month = dy.held_year_month
left join dam_yearly_cluster dc
  on l.dam_id = dc.dam_id
  and l.held_year_month = dc.held_year_month
  and l.course_cluster = dc.course_cluster
