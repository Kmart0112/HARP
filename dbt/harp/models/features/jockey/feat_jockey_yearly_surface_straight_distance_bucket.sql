{{ config(
  materialized='incremental',
  unique_key=['jockey_cd', 'held_year_month', 'surface', 'straight_distance_bucket'],
  indexes=[{'columns': ['jockey_cd', 'held_year_month', 'surface', 'straight_distance_bucket']}],
  tags=['feature','monthly']
) }}

with incremental_bounds as (
  {{ monthly_incremental_bounds(this, history_years=3) }}
),

base as (
  select
    jockey_cd,
    held_year_month,
    surface,
    case
      when straight_distance_m is null then null
      when straight_distance_m < 300 then 1
      when straight_distance_m < 350 then 2
      when straight_distance_m < 400 then 3
      when straight_distance_m < 500 then 4
      else 5
    end as straight_distance_bucket,
    is_place
  from {{ ref('int_race_entry_enriched') }}
  where held_year_month is not null
    and jockey_cd is not null
    and surface is not null
    and straight_distance_m is not null
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_jockey_surface_straight_distance_bucket as (
  select
    jockey_cd,
    held_year_month,
    surface,
    straight_distance_bucket,
    count(*) as starts,
    sum(is_place) as places
  from base
  group by
    jockey_cd,
    held_year_month,
    surface,
    straight_distance_bucket
),

yearly_jockey_surface_straight_distance_bucket_roll as (
  select
    yjssdb.*,
    sum(yjssdb.starts) over (
      partition by yjssdb.jockey_cd, yjssdb.surface, yjssdb.straight_distance_bucket
      order by yjssdb.held_year_month
      rows between 35 preceding and 1 preceding
    ) as jockey_surface_straight_distance_bucket_starts_3y,
    sum(yjssdb.places) over (
      partition by yjssdb.jockey_cd, yjssdb.surface, yjssdb.straight_distance_bucket
      order by yjssdb.held_year_month
      rows between 35 preceding and 1 preceding
    ) as jockey_surface_straight_distance_bucket_places_3y
  from yearly_jockey_surface_straight_distance_bucket yjssdb
)

select
  jockey_cd,
  held_year_month,
  surface,
  straight_distance_bucket,
  jockey_surface_straight_distance_bucket_starts_3y,
  jockey_surface_straight_distance_bucket_places_3y,
  case
    when jockey_surface_straight_distance_bucket_starts_3y is null
      or jockey_surface_straight_distance_bucket_starts_3y = 0 then null
    else
      jockey_surface_straight_distance_bucket_places_3y::float
      / nullif(jockey_surface_straight_distance_bucket_starts_3y, 0)
  end as jockey_surface_straight_distance_bucket_place_rate_3y,
  case
    when jockey_surface_straight_distance_bucket_starts_3y is null
      or jockey_surface_straight_distance_bucket_starts_3y = 0 then null
    else
      (
        jockey_surface_straight_distance_bucket_places_3y + (0.213 * 10)
      )::float
      / nullif(jockey_surface_straight_distance_bucket_starts_3y + 10, 0)
  end as jockey_surface_straight_distance_bucket_place_rate_3y_smooth
from yearly_jockey_surface_straight_distance_bucket_roll
{% if is_incremental() %}
where held_year_month >= (select recalc_from_period from incremental_bounds)
{% endif %}
