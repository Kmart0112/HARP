{{ config(
  materialized='incremental',
  unique_key=['damsire_id', 'held_year_month', 'course_cluster'],
  indexes=[{'columns': ['damsire_id', 'held_year_month', 'course_cluster']}],
  tags=['feature','monthly']
) }}

with incremental_bounds as (
  {{ monthly_incremental_bounds(this, history_years=var('sire_sample_years')) }}
),

base as (
  select
    damsire_id,
    held_year_month,
    course_cluster,
    is_place,
    is_win,
    pos4_agari_synergy,
    time_diff
  from {{ ref('feat_race_entry_base') }}
  where held_year_month is not null
    and damsire_id is not null
    and damsire_id <> 0
    and course_cluster is not null
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_damsire_cluster as (
  select
    damsire_id,
    held_year_month,
    course_cluster,
    count(*) as starts,
    sum(is_place) as places,
    sum(is_win) as wins,
    sum(time_diff) as time_diffs,
    sum(pos4_agari_synergy) as pos4_agari_synergy_sum,
    count(pos4_agari_synergy) as pos4_agari_synergy_count
  from base
  group by
    damsire_id,
    held_year_month,
    course_cluster
),

yearly_damsire_cluster_roll as (
  select
    ydc.*,
    sum(ydc.starts) over (
      partition by ydc.damsire_id, ydc.course_cluster
      order by ydc.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_cluster_damsire_starts_5y,
    sum(ydc.places) over (
      partition by ydc.damsire_id, ydc.course_cluster
      order by ydc.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_cluster_damsire_places_5y,
    sum(ydc.wins) over (
      partition by ydc.damsire_id, ydc.course_cluster
      order by ydc.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_cluster_damsire_wins_5y,
    sum(ydc.time_diffs) over (
      partition by ydc.damsire_id, ydc.course_cluster
      order by ydc.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_cluster_damsire_time_diffs_5y,
    sum(ydc.pos4_agari_synergy_sum) over (
      partition by ydc.damsire_id, ydc.course_cluster
      order by ydc.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_cluster_damsire_pos4_agari_synergy_sum_5y,
    sum(ydc.pos4_agari_synergy_count) over (
      partition by ydc.damsire_id, ydc.course_cluster
      order by ydc.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_cluster_damsire_pos4_agari_synergy_count_5y
  from yearly_damsire_cluster ydc
)

select
  damsire_id,
  held_year_month,
  course_cluster,
  same_cluster_damsire_starts_5y,
  same_cluster_damsire_places_5y,
  same_cluster_damsire_wins_5y,
  same_cluster_damsire_time_diffs_5y,
  same_cluster_damsire_places_5y::float
    / nullif(same_cluster_damsire_starts_5y, 0) as same_cluster_damsire_avg_place_rate,
  ((same_cluster_damsire_places_5y + (0.213 * 50))::float
    / nullif(same_cluster_damsire_starts_5y + 50, 0)) as same_cluster_damsire_avg_place_rate_smooth,
  same_cluster_damsire_pos4_agari_synergy_sum_5y::float
    / nullif(same_cluster_damsire_pos4_agari_synergy_count_5y, 0) as same_cluster_damsire_avg_pos4_agari_synergy
from yearly_damsire_cluster_roll
{% if is_incremental() %}
where held_year_month >= (select recalc_from_period from incremental_bounds)
{% endif %}
