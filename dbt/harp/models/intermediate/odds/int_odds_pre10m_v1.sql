{{ config(materialized='incremental', unique_key=['race_id','horse_number'],
  incremental_strategy='delete+insert', on_schema_change='fail',
  tags=['odds_contract_v1', 'training'],
  indexes=[{'columns':['race_id','horse_number'],'unique':True}, {'columns':['held_date']}]) }}
with races as (
  select race_id, held_date, (held_date + hassotime) at time zone 'Asia/Tokyo' as scheduled_start_at
  from {{ ref('fct_race_basic') }}
  where 1=1
  {% if var('target_held_date', none) is not none %}
    and held_date = '{{ var("target_held_date") }}'::date
  {% else %}
    {% if var('race_from_date', none) is not none %}
      and held_date >= '{{ var("race_from_date") }}'::date
    {% else %}
      and held_date >= current_date - interval '7 days'
    {% endif %}
    {% if var('race_to_date', none) is not none %}and held_date <= '{{ var("race_to_date") }}'::date{% endif %}
  {% endif %}
), entries as (
  select e.race_id, e.horse_number, r.held_date, r.scheduled_start_at
  from {{ ref('m_race_inputs_v1') }} e
  join races r using (race_id, held_date)
  where not e.is_scratched
), candidates as materialized (
  select o.*, r.scheduled_start_at - interval '10 minutes' as cutoff_at,
    dense_rank() over (partition by o.race_id, o.horse_number order by o.odds_published_at desc) as publication_rank
  from {{ ref('stg_n_odds_quotes_v1') }} o
  join races r using (race_id, held_date)
  where o.source_year >= (select min(extract(year from held_date))::integer::text from races)
    and o.source_year <= (select max(extract(year from held_date))::integer::text from races)
    and o.odds_published_at <= r.scheduled_start_at - interval '10 minutes'
)
-- Missing publications overwrite an older cached quote on incremental reruns.
-- All requested entrants remain observable, including unknown start times.
select e.race_id, e.horse_number, e.held_date, o.odds_published_at, o.available_at,
       o.odds_tansho, o.odds_fukusho_low, o.odds_fukusho_high, o.popularity,
       e.scheduled_start_at - interval '10 minutes' as cutoff_at
from entries e
left join candidates o on e.race_id=o.race_id and e.horse_number=o.horse_number and o.publication_rank=1
