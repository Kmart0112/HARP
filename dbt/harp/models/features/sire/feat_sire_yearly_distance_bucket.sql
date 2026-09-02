{{ config(materialized='table', tags=['feature','monthly'], enabled=false) }}

with base as (
  select
    sire_id,
    held_year_month,
    case
      when distance_m < 1400 then 1
      when distance_m < 1800 then 2
      when distance_m < 2200 then 3
      else 4
    end as distance_bucket_cd,
    is_place,
    is_win
  from {{ ref('int_race_entry_enriched') }}
  where held_year_month is not null
    and sire_id is not null
    and distance_m is not null
),

yearly_sire_distance_bucket as (
  select
    sire_id,
    held_year_month,
    distance_bucket_cd,
    count(*) as starts,
    sum(is_place) as places,
    sum(is_win) as wins
  from base
  group by
    sire_id,
    held_year_month,
    distance_bucket_cd
),

yearly_sire_distance_bucket_roll as (
  select
    ysdb.*,
    sum(ysdb.starts) over (
      partition by ysdb.sire_id, ysdb.distance_bucket_cd
      order by ysdb.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_dist_bucket_sire_starts_5y,
    sum(ysdb.places) over (
      partition by ysdb.sire_id, ysdb.distance_bucket_cd
      order by ysdb.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_dist_bucket_sire_places_5y,
    sum(ysdb.wins) over (
      partition by ysdb.sire_id, ysdb.distance_bucket_cd
      order by ysdb.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_dist_bucket_sire_wins_5y
  from yearly_sire_distance_bucket ysdb
)

select
  sire_id,
  held_year_month,
  distance_bucket_cd,
  same_dist_bucket_sire_starts_5y,
  same_dist_bucket_sire_places_5y,
  same_dist_bucket_sire_wins_5y,
  same_dist_bucket_sire_places_5y::float / nullif(same_dist_bucket_sire_starts_5y, 0) as same_dist_bucket_sire_place_rate_5y
from yearly_sire_distance_bucket_roll
