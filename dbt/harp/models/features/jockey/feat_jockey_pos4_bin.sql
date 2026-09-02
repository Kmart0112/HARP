{{ config(
  materialized='incremental',
  unique_key=['jockey_cd', 'held_year_month', 'pos4_bin5'],
  indexes=[{'columns': ['jockey_cd', 'held_year_month', 'pos4_bin5']}],
  tags=['feature','monthly']
) }}

with incremental_bounds as (
  {{ monthly_incremental_bounds(this, history_years=3) }}
),

base as (
  select
    jockey_cd,
    held_year_month,
    case
      when corner4_pos is null then null
      when corner4_pos < 0.2 then 1
      when corner4_pos < 0.4 then 2
      when corner4_pos < 0.6 then 3
      when corner4_pos < 0.8 then 4
      else 5
    end as pos4_bin5,
    is_place
  from {{ ref('int_race_entry_enriched') }}
  where held_year_month is not null
    and jockey_cd is not null
    and corner4_pos is not null
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_jockey_pos4_bin as (
  select
    jockey_cd,
    held_year_month,
    pos4_bin5,
    count(*) as starts,
    sum(is_place) as places
  from base
  group by
    jockey_cd,
    held_year_month,
    pos4_bin5
),

yearly_overall_pos4_bin as (
  select
    held_year_month,
    pos4_bin5,
    count(*) as starts,
    sum(is_place) as places
  from base
  group by
    held_year_month,
    pos4_bin5
),

yearly_jockey_pos4_bin_cum as (
  select
    yjpb.*,
    sum(yjpb.starts) over (
      partition by yjpb.jockey_cd, yjpb.pos4_bin5
      order by yjpb.held_year_month
      rows between 35 preceding and 1 preceding
    ) as jockey_pos4_bin5_starts_3y,
    sum(yjpb.places) over (
      partition by yjpb.jockey_cd, yjpb.pos4_bin5
      order by yjpb.held_year_month
      rows between 35 preceding and 1 preceding
    ) as jockey_pos4_bin5_places_3y
  from yearly_jockey_pos4_bin yjpb
),

overall_cum as (
  select
    yopb.*,
    sum(yopb.starts) over (
      partition by yopb.pos4_bin5
      order by yopb.held_year_month
      rows between 35 preceding and 1 preceding
    ) as overall_pos4_bin5_starts_3y,
    sum(yopb.places) over (
      partition by yopb.pos4_bin5
      order by yopb.held_year_month
      rows between 35 preceding and 1 preceding
    ) as overall_pos4_bin5_places_3y
  from yearly_overall_pos4_bin yopb
),

overall_pos4_bin_place_rate as (
  select
    held_year_month,
    pos4_bin5,
    overall_pos4_bin5_starts_3y,
    overall_pos4_bin5_places_3y,
    overall_pos4_bin5_places_3y::float / nullif(overall_pos4_bin5_starts_3y, 0) as overall_pos4_bin5_place_rate_3y,
    ((overall_pos4_bin5_places_3y + (0.213 * 10))::float / nullif(overall_pos4_bin5_starts_3y + 10, 0)) as overall_pos4_bin5_place_rate_3y_smooth
  from overall_cum
)

select
  jockey_cd,
  held_year_month,
  pos4_bin5,
  jockey_pos4_bin5_starts_3y,
  jockey_pos4_bin5_places_3y,
  jockey_pos4_bin5_places_3y::float / nullif(jockey_pos4_bin5_starts_3y, 0) as jockey_pos4_bin5_place_rate_3y,
  ((jockey_pos4_bin5_places_3y + (0.213 * 10))::float / nullif(jockey_pos4_bin5_starts_3y + 10, 0)) as jockey_pos4_bin5_place_rate_3y_smooth,
  oppr.overall_pos4_bin5_starts_3y,
  oppr.overall_pos4_bin5_places_3y,
  oppr.overall_pos4_bin5_place_rate_3y_smooth,
  (((jockey_pos4_bin5_places_3y + (0.213 * 10))::float / nullif(jockey_pos4_bin5_starts_3y + 10, 0)) / oppr.overall_pos4_bin5_place_rate_3y_smooth) as jockey_pos4_bin5_relative_place_rate_3y_smooth
from yearly_jockey_pos4_bin_cum yjpc
join overall_pos4_bin_place_rate oppr
  using (held_year_month, pos4_bin5)
{% if is_incremental() %}
where held_year_month >= (select recalc_from_period from incremental_bounds)
{% endif %}
