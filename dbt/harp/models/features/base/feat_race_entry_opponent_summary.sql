{{ config(
  materialized='table',
  tags=['nn_inputs', 'nn_history'],
  indexes=[{'columns': ['race_id', 'kettonum'], 'unique': True}]
) }}

-- Start with the complete stored actual-run field, not the selected target
-- horses/date range. Missing statistics must not remove an opponent.
with profiles as (
  select
    r.race_id,
    r.kettonum,
    r.held_date,
    case when h.past_starts > 0 then h.past_places::float / h.past_starts end as horse_rate,
    h.past_starts as horse_starts,
    case when r.jockey_starts_3y > 0 then r.jockey_place_rate_3y_smooth end as jockey_rate,
    r.jockey_starts_3y as jockey_starts
  from {{ ref('int_race_entry_run_record') }} r
  left join {{ ref('feat_horse_overall') }} h
    on r.kettonum = h.kettonum and r.held_date = h.held_date
),

ranked as (
  select
    *,
    row_number() over (partition by race_id order by horse_rate desc nulls last, kettonum) as horse_rank,
    row_number() over (partition by race_id order by jockey_rate desc nulls last, kettonum) as jockey_rank
  from profiles
),

race_stats as (
  select
    race_id,
    count(*) as field_count,
    {% for entity in ['horse', 'jockey'] %}
    count({{ entity }}_rate) as {{ entity }}_known,
    coalesce(sum({{ entity }}_rate), 0) as {{ entity }}_sum,
    coalesce(sum({{ entity }}_starts) filter (where {{ entity }}_rate is not null), 0) as {{ entity }}_starts_sum,
    array_agg({{ entity }}_rate order by {{ entity }}_rank)
      filter (where {{ entity }}_rate is not null and {{ entity }}_rank <= 4) as {{ entity }}_top_rates,
    array_agg(kettonum order by {{ entity }}_rank)
      filter (where {{ entity }}_rate is not null and {{ entity }}_rank <= 4) as {{ entity }}_top_ids,
    {% endfor %}
    coalesce(sum(horse_rate * horse_rate), 0) as horse_sum_sq
  from ranked
  group by race_id
),

opponents as (
  select
    p.race_id,
    p.kettonum,
    p.held_date,
    s.field_count - 1 as opp_count,
    {% for entity in ['horse', 'jockey'] %}
    s.{{ entity }}_known - case when p.{{ entity }}_rate is not null then 1 else 0 end as {{ entity }}_count,
    s.{{ entity }}_sum - coalesce(p.{{ entity }}_rate, 0) as {{ entity }}_sum,
    s.{{ entity }}_starts_sum - case when p.{{ entity }}_rate is not null then p.{{ entity }}_starts else 0 end as {{ entity }}_starts_sum,
    (
      select avg(top.rate)
      from (
        select t.rate
        from unnest(s.{{ entity }}_top_rates, s.{{ entity }}_top_ids) as t(rate, horse_id)
        where t.horse_id <> p.kettonum
        order by t.rate desc
        limit 3
      ) top
    ) as {{ entity }}_top3_mean,
    {% endfor %}
    s.horse_sum_sq - coalesce(p.horse_rate * p.horse_rate, 0) as horse_sum_sq
  from profiles p
  join race_stats s on p.race_id = s.race_id
)

select
  race_id,
  kettonum,
  held_date,
  opp_count,
  horse_sum / nullif(horse_count, 0) as opp_horse_place_mean,
  horse_top3_mean as opp_horse_place_top3_mean,
  case
    when horse_count = 0 then null
    when horse_count = 1 then 0::float
    else sqrt(greatest(horse_sum_sq / horse_count - power(horse_sum / horse_count, 2), 0))
  end as opp_horse_place_std,
  horse_starts_sum::float / nullif(horse_count, 0) as opp_horse_starts_mean,
  horse_count::float / nullif(opp_count, 0) as opp_horse_place_coverage,
  jockey_sum / nullif(jockey_count, 0) as opp_jockey_place_mean,
  jockey_top3_mean as opp_jockey_place_top3_mean,
  jockey_starts_sum::float / nullif(jockey_count, 0) as opp_jockey_starts_mean,
  jockey_count::float / nullif(opp_count, 0) as opp_jockey_place_coverage
from opponents
