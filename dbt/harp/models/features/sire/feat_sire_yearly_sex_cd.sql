{{ config(
  materialized='incremental',
  unique_key=['sire_id', 'held_year_month', 'sex_cd'],
  indexes=[{'columns': ['sire_id', 'held_year_month', 'sex_cd']}],
  tags=['feature','monthly']
) }}

with incremental_bounds as (
  {{ monthly_incremental_bounds(this, history_years=var('sire_sample_years')) }}
),

base as (
  select
    sire_id,
    held_year_month,
    sex_cd,
    is_place,
    pos4_agari_synergy
  from {{ ref('feat_race_entry_base') }}
  where held_year_month is not null
    and sire_id is not null
    and sex_cd is not null
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

sex_cd_yearly as (
  select
    *
  from {{ ref('feat_sex_cd_yearly') }}
),

yearly_sire_sex_cd as (
  select
    sire_id,
    held_year_month,
    sex_cd,
    count(*) as starts,
    sum(is_place) as places,
    sum(pos4_agari_synergy) as pos4_agari_synergy_sum,
    count(pos4_agari_synergy) as pos4_agari_synergy_count
  from base
  group by
    sire_id,
    held_year_month,
    sex_cd
),

yearly_sire_sex_cd_with_prior as (
  select
    yssc.*,
    scy.sex_cd_place_rate_3y as sex_cd_place_rate_3y_prior
  from yearly_sire_sex_cd yssc
  left join sex_cd_yearly scy
    on yssc.sex_cd = scy.sex_cd
    and extract(year from yssc.held_year_month)::int = scy.held_year
),

yearly_sire_sex_cd_roll as (
  select
    ysscp.*,
    sum(ysscp.starts) over (
      partition by ysscp.sire_id, ysscp.sex_cd
      order by ysscp.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_sex_cd_sire_starts_5y,
    sum(ysscp.places) over (
      partition by ysscp.sire_id, ysscp.sex_cd
      order by ysscp.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_sex_cd_sire_places_5y,
    sum(ysscp.pos4_agari_synergy_sum) over (
      partition by ysscp.sire_id, ysscp.sex_cd
      order by ysscp.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_sex_cd_sire_pos4_agari_synergy_sum_5y,
    sum(ysscp.pos4_agari_synergy_count) over (
      partition by ysscp.sire_id, ysscp.sex_cd
      order by ysscp.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_sex_cd_sire_pos4_agari_synergy_count_5y
  from yearly_sire_sex_cd_with_prior ysscp
)

select
  sire_id,
  held_year_month,
  sex_cd,
  same_sex_cd_sire_starts_5y,
  same_sex_cd_sire_places_5y,
  sex_cd_place_rate_3y_prior,
  same_sex_cd_sire_pos4_agari_synergy_sum_5y::float
    / nullif(same_sex_cd_sire_pos4_agari_synergy_count_5y, 0)
    as same_sex_cd_sire_avg_pos4_agari_synergy,
  (
    (
      coalesce(same_sex_cd_sire_places_5y, 0)
      + (coalesce(sex_cd_place_rate_3y_prior, 0.213) * 20)
    )::float
    / nullif(coalesce(same_sex_cd_sire_starts_5y, 0) + 20, 0)
  ) as same_sex_cd_sire_avg_place_rate_smooth_prev_sex_cd
from yearly_sire_sex_cd_roll
{% if is_incremental() %}
where held_year_month >= (select recalc_from_period from incremental_bounds)
{% endif %}
