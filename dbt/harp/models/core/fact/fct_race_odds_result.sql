{{ config(materialized='table',tags=['prd']) }}

-- TODO: 先にstg_jodds_tanpukuを作成すること
with base as (
select
    *
    from {{ ref('stg_n_odds_tanpuku') }}
),

unioned as (
    select
        race_id,
        horse_number,
        odds_tansho,
        odds_fukusho_low,
        odds_fukusho_high,
        2 as src_priority
    from base
    union all
    select
        race_id,
        horse_number,
        odds_tansho,
        odds_fukusho_low,
        odds_fukusho_high,
        1 as src_priority
    from {{ ref('int_s_jodds_latest') }}
),

deduped as (
    select distinct on (race_id, horse_number)
        race_id,
        horse_number,
        odds_tansho,
        odds_fukusho_low,
        odds_fukusho_high
    from unioned
    order by race_id, horse_number, src_priority asc
)

select
    d.race_id,
    d.horse_number,
    d.odds_tansho,
    d.odds_fukusho_low,
    d.odds_fukusho_high,
    case
    when d.odds_fukusho_low is not null and d.odds_fukusho_high is not null then
        (d.odds_fukusho_low + d.odds_fukusho_high) / 2.0
    else
        null
    end as odds_fukusho_avg,
    case
    when d.odds_fukusho_low is not null and d.odds_fukusho_high is not null then
        0.7 * d.odds_fukusho_low + 0.3 * d.odds_fukusho_high
    else
        null
    end as odds_fukusho_weighted_avg,
    case 
    when tansyo_umaban1 = d.horse_number then tansyo_pay1
    when tansyo_umaban2 = d.horse_number then tansyo_pay2
    else 0
    end as pay_tansho,
    case 
    when fukusyo_umaban1 = d.horse_number then fukusyo_pay1
    when fukusyo_umaban2 = d.horse_number then fukusyo_pay2
    when fukusyo_umaban3 = d.horse_number then fukusyo_pay3
    when fukusyo_umaban4 = d.horse_number then fukusyo_pay4
    when fukusyo_umaban5 = d.horse_number then fukusyo_pay5
    else 0
    end as pay_fukusho,

    j.odds_tansho as j_odds_tansho,
    j.popularity as j_popularity,
    j.odds_fukusho_low as j_odds_fukusho_low,
    j.odds_fukusho_high as j_odds_fukusho_high,
    case 
    when j.odds_fukusho_low is not null and j.odds_fukusho_high is not null then
        (j.odds_fukusho_low + j.odds_fukusho_high) / 2.0
    else
        null
    end as j_odds_fukusho_avg,
    case 
    when j.odds_fukusho_low is not null and j.odds_fukusho_high is not null then
        j.odds_fukusho_low*0.7 + j.odds_fukusho_high*0.3
    else
        null
    end as j_odds_fukusho_weighted_avg
from deduped d
left join {{ ref('stg_n_harai') }} h
    on d.race_id = h.race_id
left join {{ source('published_manual', 'fct_jodds_snapshot') }} j
      on d.race_id = j.race_id
    and d.horse_number = j.horse_number
