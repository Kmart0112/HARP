-- サイアー×コースクラスター横持
-- サイアー毎にコースクラスター別の成績を算出する
{{ config(
    materialized='table',
    unique_key='sire_id'
) }}
with base as (
    select
        re.sire_id,
        re.course_cluster,
        count(*) as total_runs,
        sum(case when re.result_order = 1 then 1 else 0 end) as wins,
        sum(case when re.result_order <= 3 and re.result_order > 0 then 1 else 0 end) as places
    from {{ ref('m_train_race_horse_past5') }} re
    group by 1, 2
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

-- 横持に変換
pivoted as (
    select
        sire_id,
        max(case when course_cluster = 0 then total_runs else 0 end) as runs_cluster_0,
        max(case when course_cluster = 0 then wins else 0 end) as wins_cluster_0,
        max(case when course_cluster = 0 then places else 0 end) as places_cluster_0,
        max(case when course_cluster = 1 then total_runs else 0 end) as runs_cluster_1,
        max(case when course_cluster = 1 then wins else 0 end) as wins_cluster_1,
        max(case when course_cluster = 1 then places else 0 end) as places_cluster_1,
        max(case when course_cluster = 2 then total_runs else 0 end) as runs_cluster_2,
        max(case when course_cluster = 2 then wins else 0 end) as wins_cluster_2,
        max(case when course_cluster = 2 then places else 0 end) as places_cluster_2,
        max(case when course_cluster = 3 then total_runs else 0 end) as runs_cluster_3,
        max(case when course_cluster = 3 then wins else 0 end) as wins_cluster_3,
        max(case when course_cluster = 3 then places else 0 end) as places_cluster_3,
        max(case when course_cluster = 4 then total_runs else 0 end) as runs_cluster_4,
        max(case when course_cluster = 4 then wins else 0 end) as wins_cluster_4,
        max(case when course_cluster = 4 then places else 0 end) as places_cluster_4,
        max(case when course_cluster = 5 then total_runs else 0 end) as runs_cluster_5,
        max(case when course_cluster = 5 then wins else 0 end) as wins_cluster_5,
        max(case when course_cluster = 5 then places else 0 end) as places_cluster_5,
        max(case when course_cluster = 6 then total_runs else 0 end) as runs_cluster_6,
        max(case when course_cluster = 6 then wins else 0 end) as wins_cluster_6,
        max(case when course_cluster = 6 then places else 0 end) as places_cluster_6

    from base
    group by sire_id
),

summary as   (
    select
    *,
    wins_cluster_0/nullif(runs_cluster_0::float, 0) as win_rate_cluster_0,
    places_cluster_0/nullif(runs_cluster_0::float, 0) as place_rate_cluster_0,
    wins_cluster_1/nullif(runs_cluster_1::float, 0) as win_rate_cluster_1,
    places_cluster_1/nullif(runs_cluster_1::float, 0) as place_rate_cluster_1,
    wins_cluster_2/nullif(runs_cluster_2::float, 0) as win_rate_cluster_2,
    places_cluster_2/nullif(runs_cluster_2::float, 0) as place_rate_cluster_2,
    wins_cluster_3/nullif(runs_cluster_3::float, 0) as win_rate_cluster_3,
    places_cluster_3/nullif(runs_cluster_3::float, 0) as place_rate_cluster_3,
    wins_cluster_4/nullif(runs_cluster_4::float, 0) as win_rate_cluster_4,
    places_cluster_4/nullif(runs_cluster_4::float, 0) as place_rate_cluster_4,
    wins_cluster_5/nullif(runs_cluster_5::float, 0) as win_rate_cluster_5,
    places_cluster_5/nullif(runs_cluster_5::float, 0) as place_rate_cluster_5,
    wins_cluster_6/nullif(runs_cluster_6::float, 0) as win_rate_cluster_6,
    places_cluster_6/nullif(runs_cluster_6::float, 0) as place_rate_cluster_6
from pivoted)


select
    s.*,
    sa.total_runs_all,
    sa.wins_all,
    sa.places_all,
    sa.win_rate_all,
    sa.place_rate_all,
    s.win_rate_cluster_0 - sa.win_rate_all as win_rate_diff_cluster_0,
    s.place_rate_cluster_0 - sa.place_rate_all as place_rate_diff_cluster_0,
    s.win_rate_cluster_1 - sa.win_rate_all as win_rate_diff_cluster_1,
    s.place_rate_cluster_1 - sa.place_rate_all as place_rate_diff_cluster_1,
    s.win_rate_cluster_2 - sa.win_rate_all as win_rate_diff_cluster_2,
    s.place_rate_cluster_2 - sa.place_rate_all as place_rate_diff_cluster_2,
    s.win_rate_cluster_3 - sa.win_rate_all as win_rate_diff_cluster_3,
    s.place_rate_cluster_3 - sa.place_rate_all as place_rate_diff_cluster_3,
    s.win_rate_cluster_4 - sa.win_rate_all as win_rate_diff_cluster_4,
    s.place_rate_cluster_4 - sa.place_rate_all as place_rate_diff_cluster_4,
    s.win_rate_cluster_5 - sa.win_rate_all as win_rate_diff_cluster_5,
    s.place_rate_cluster_5 - sa.place_rate_all as place_rate_diff_cluster_5,
    s.win_rate_cluster_6 - sa.win_rate_all as win_rate_diff_cluster_6,
    s.place_rate_cluster_6 - sa.place_rate_all as place_rate_diff_cluster_6
from summary s
join sire_all sa
    using (sire_id)
