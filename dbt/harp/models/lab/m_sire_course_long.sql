{{ config(
    materialized='table',
    unique_key='sire_id'
) }}
with base as (
    select
        re.sire_id,
        re.course_cluster,
        re.sire_name,
        count(*) as total_runs,
        sum(case when re.result_order = 1 then 1 else 0 end) as wins,
        sum(case when re.result_order <= 3 and re.result_order > 0 then 1 else 0 end) as places
    from {{ ref('m_train_race_horse_past5') }} re
    group by 1, 2, 3
),
sire_all as (
    select
        sire_id,
        sum(total_runs) as total_runs_all,
        sum(wins) as wins_all,
        sum(places) as places_all,
        sum(wins)::float/nullif(sum(total_runs)::float, 0) as win_rate_all,
        sum(places)::float/nullif(sum(total_runs)::float, 0) as place_rate_all
    from base
    group by sire_id
),

long as (select
    b.sire_id,
    b.sire_name,
    b.course_cluster,
    b.total_runs,
    b.wins,
    b.places,
    s.total_runs_all,
    s.wins_all,
    s.places_all,
    s.win_rate_all,
    s.place_rate_all,
    b.wins/nullif(b.total_runs::float, 0) as win_rate_cluster,
    b.places/nullif(b.total_runs::float, 0) as place_rate_cluster
    from base b
    join sire_all s
      on b.sire_id = s.sire_id
)

select
  *,
  win_rate_cluster-win_rate_all as win_rate_diff,
    place_rate_cluster-place_rate_all as place_rate_diff
from long