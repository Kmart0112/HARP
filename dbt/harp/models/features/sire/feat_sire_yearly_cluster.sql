-- 種牡馬×コースクラスタ別の年次成績（過去{{ var('sire_sample_years') }}年移動平均）
{{ config(
  materialized='incremental',
  unique_key=['sire_id', 'held_year_month', 'course_cluster'],
  indexes=[{'columns': ['sire_id', 'held_year_month', 'course_cluster']}],
  tags=['feature','monthly']
) }}

with incremental_bounds as (
  {{ monthly_incremental_bounds(this, history_years=var('sire_sample_years')) }}
),

base as (
  select
    sire_id,
    held_year_month,
    course_cluster,
    is_place,
    is_win,
    time_diff,
    pos4_agari_synergy
  from {{ ref('feat_race_entry_base') }}
  where held_year_month is not null
    and sire_id is not null
    and course_cluster is not null
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_sire_cluster as (
  select
    sire_id,
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
    sire_id,
    held_year_month,
    course_cluster
),

yearly_sire_cluster_roll as (
  select
    ysc.*,
    sum(ysc.starts) over (
      partition by ysc.sire_id, ysc.course_cluster
      order by ysc.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_cluster_sire_starts_5y,
    sum(ysc.places) over (
      partition by ysc.sire_id, ysc.course_cluster
      order by ysc.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_cluster_sire_places_5y,
    sum(ysc.wins) over (
      partition by ysc.sire_id, ysc.course_cluster
      order by ysc.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_cluster_sire_wins_5y,
    sum(ysc.time_diffs) over (
      partition by ysc.sire_id, ysc.course_cluster
      order by ysc.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_cluster_sire_time_diffs_5y,
    sum(ysc.pos4_agari_synergy_sum) over (
      partition by ysc.sire_id, ysc.course_cluster
      order by ysc.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_cluster_sire_pos4_agari_synergy_sum_5y,
    sum(ysc.pos4_agari_synergy_count) over (
      partition by ysc.sire_id, ysc.course_cluster
      order by ysc.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_cluster_sire_pos4_agari_synergy_count_5y
  from yearly_sire_cluster ysc
)

select
  sire_id,
  held_year_month,
  course_cluster,
  same_cluster_sire_starts_5y,
  same_cluster_sire_places_5y,
  same_cluster_sire_wins_5y,
  same_cluster_sire_time_diffs_5y,
  same_cluster_sire_pos4_agari_synergy_sum_5y::float
    / nullif(same_cluster_sire_pos4_agari_synergy_count_5y, 0)
    as same_cluster_sire_avg_pos4_agari_synergy
from yearly_sire_cluster_roll
{% if is_incremental() %}
where held_year_month >= (select recalc_from_period from incremental_bounds)
{% endif %}
