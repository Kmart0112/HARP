{{config(
    materialized='table',
    tags=['prd']
)}}

select 
    race_id,
    r.held_date,
    case
        when r.jyo_cd = 1 then '札幌'
        when r.jyo_cd = 2 then '函館'
        when r.jyo_cd = 3 then '福島'
        when r.jyo_cd = 4 then '新潟'
        when r.jyo_cd = 5 then '東京'
        when r.jyo_cd = 6 then '中山'
        when r.jyo_cd = 7 then '中京'
        when r.jyo_cd = 8 then '京都'
        when r.jyo_cd = 9 then '阪神'
        when r.jyo_cd = 10 then '小倉'
        else 'その他'
    end as jyo_name,
    r.round,
    r.name as race_name,
    r.distance_m,
    r.surface,
    r.surface_condition,
    re.kettonum,
    re.horse_name,
    re.horse_number,
    re.age,
    re.popularity



from {{ ref('fct_race_entry') }} re
left join {{ ref('fct_race') }} r
    using (race_id)