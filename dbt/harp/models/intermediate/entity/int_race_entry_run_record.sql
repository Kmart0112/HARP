{{ config(
  materialized='table',
  tags=['nn_inputs', 'nn_history'],
  indexes=[
    {'columns': ['race_id', 'kettonum'], 'unique': True},
    {'columns': ['kettonum', 'run_no'], 'unique': True},
    {'columns': ['kettonum', 'held_date', 'run_no']}
  ]
) }}

-- Rebuild from ALL stored pre-race rows, even when targets are date-filtered.
-- Backfills can renumber a horse's whole sequence; run_no is not a durable ID.
with runs as (
  select
    p.race_id,
    p.kettonum,
    p.held_date,
    {{ nn_select_pre_race_features('p') }},
    {{ nn_select_stats_metadata('p') }},
    p.ijyo_cd as result_status_code,
    coalesce(r.result_order, a.result_order) as result_order,
    coalesce(r.time_sec, a.time_sec) as time_sec,
    coalesce(r.time_diff, a.time_diff) as time_diff,
    coalesce(r.agari3f, a.agari3f) as agari3f,
    coalesce(r.rank_1c, a.rank_1c) as rank_1c,
    coalesce(r.rank_2c, a.rank_2c) as rank_2c,
    coalesce(r.rank_3c, a.rank_3c) as rank_3c,
    coalesce(r.rank_4c, a.rank_4c) as rank_4c,
    coalesce(r.running_style_cd, a.running_style_cd) as running_style_cd
  from {{ ref('feat_race_entry_pre_race') }} p
  left join {{ ref('fct_race_entry_result') }} r
    on p.race_id = r.race_id and p.kettonum = r.kettonum
  -- The result fact only contains finishing positions. Preserve known abnormal
  -- starts (including DNF) using the unfiltered, normalized source as fallback.
  left join {{ ref('stg_n_uma_race_all') }} a
    on p.race_id = a.race_id and p.kettonum = a.kettonum
   and r.race_id is null
  -- JV-Data 2101: 1/2/3 are nonstarters; 4/5/6/7 actually started.
  -- https://jra-van.jp/dlb/sdv/sdk/JV-Data4901.pdf
  where coalesce(p.ijyo_cd, '0') not in ('1', '2', '3')
    and (r.race_id is not null or p.ijyo_cd in ('4', '5', '6', '7'))
)

select
  race_id,
  kettonum,
  held_date,
  row_number() over (
    partition by kettonum order by held_date, race_id
  ) as run_no,
  {{ nn_select_pre_race_features('runs') }},
  monthly_stats_cutoff,
  yearly_stats_cutoff,
  jockey_stats_missing,
  trainer_stats_missing,
  breeder_stats_missing,
  sire_stats_missing,
  dam_stats_missing,
  damsire_stats_missing,
  result_status_code,
  result_order,
  time_sec,
  time_diff,
  agari3f,
  rank_1c,
  rank_2c,
  rank_3c,
  rank_4c,
  running_style_cd
from runs
