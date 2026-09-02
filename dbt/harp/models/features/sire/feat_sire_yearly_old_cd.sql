{{ config(
  materialized='incremental',
  unique_key=['sire_id', 'held_year_month', 'old_cd'],
  indexes=[{'columns': ['sire_id', 'held_year_month', 'old_cd']}],
  tags=['feature','monthly']
) }}

with incremental_bounds as (
  {{ monthly_incremental_bounds(this, history_years=var('sire_sample_years')) }}
),

base as (
  select
    sire_id,
    held_year_month,
    old_cd,
    is_place,
    pos4_agari_synergy
  from {{ ref('feat_race_entry_base') }}
  where held_year_month is not null
    and sire_id is not null
    and old_cd is not null
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

old_cd_yearly as (
  select
    *
  from {{ ref('feat_old_cd_yearly') }}
),

yearly_sire_old_cd as (
  select
    sire_id,
    held_year_month,
    old_cd,
    count(*) as starts,
    sum(is_place) as places,
    sum(pos4_agari_synergy) as pos4_agari_synergy_sum,
    count(pos4_agari_synergy) as pos4_agari_synergy_count
  from base
  group by
    sire_id,
    held_year_month,
    old_cd
),

yearly_sire_old_cd_with_prior as (
  select
    ysoc.*,
    ocy.old_cd_place_rate_3y as old_cd_place_rate_3y_prior
  from yearly_sire_old_cd ysoc
  left join old_cd_yearly ocy
    on ysoc.old_cd = ocy.old_cd
    and extract(year from ysoc.held_year_month)::int = ocy.held_year
),

yearly_sire_old_cd_roll as (
  select
    ysocp.*,
    sum(ysocp.starts) over (
      partition by ysocp.sire_id, ysocp.old_cd
      order by ysocp.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_old_cd_sire_starts_5y,
    sum(ysocp.places) over (
      partition by ysocp.sire_id, ysocp.old_cd
      order by ysocp.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_old_cd_sire_places_5y,
    sum(ysocp.pos4_agari_synergy_sum) over (
      partition by ysocp.sire_id, ysocp.old_cd
      order by ysocp.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_old_cd_sire_pos4_agari_synergy_sum_5y,
    sum(ysocp.pos4_agari_synergy_count) over (
      partition by ysocp.sire_id, ysocp.old_cd
      order by ysocp.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_old_cd_sire_pos4_agari_synergy_count_5y
  from yearly_sire_old_cd_with_prior ysocp
)

select
  sire_id,
  held_year_month,
  old_cd,
  same_old_cd_sire_starts_5y,
  same_old_cd_sire_places_5y,
  old_cd_place_rate_3y_prior,
  same_old_cd_sire_pos4_agari_synergy_sum_5y::float
    / nullif(same_old_cd_sire_pos4_agari_synergy_count_5y, 0)
    as same_old_cd_sire_avg_pos4_agari_synergy,
  (
    (
      coalesce(same_old_cd_sire_places_5y, 0)
      + (coalesce(old_cd_place_rate_3y_prior, 0.213) * 20)
    )::float
    / nullif(coalesce(same_old_cd_sire_starts_5y, 0) + 20, 0)
  ) as same_old_cd_sire_avg_place_rate_smooth_prev_old_cd
from yearly_sire_old_cd_roll
{% if is_incremental() %}
where held_year_month >= (select recalc_from_period from incremental_bounds)
{% endif %}
