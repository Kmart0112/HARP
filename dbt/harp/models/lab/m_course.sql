{{ config(materialized='table') }}

with base as (
    select
        jyo_cd,
        distance_m,
        surface,
        pace_type,
        is_place,
        is_win,
        agari_good,
        agari3f,
        ten3f,
        corner4_pos,
        track_cd
    from {{ ref('feat_race_entry_base') }} 
    where race_level in (1,2,3)
    and old_cd = 0
)

select
    jyo_cd,
    distance_m,
    surface,
    track_cd,
    count(*) as total_starts,
    avg(pace_type) as avg_pace_type,
    avg(agari3f) as avg_agari3f,
    avg(ten3f) as avg_ten3f,
    avg(case when is_place = 1 then agari_good end) as agari_good_place_avg,
    avg(case when is_place = 1 then corner4_pos end) as corner4_pos_place_avg,
    avg(case when is_win = 1 then agari_good end) as agari_good_win_avg,
    avg(case when is_win = 1 then corner4_pos end) as corner4_pos_win_avg
from base
group by
    jyo_cd,
    distance_m,
    surface,
    track_cd