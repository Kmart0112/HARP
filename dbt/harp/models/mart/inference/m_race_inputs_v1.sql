{{ config(materialized='view', tags=['odds_contract_v1', 'inference']) }}
-- Model-facing entry contract. Odds are supplied through the same SQL snapshot
-- by the repository, from a separately bound quote relation.
select f.*,
       r.jyo_name,
       (f.held_date + f.hassotime) at time zone 'Asia/Tokyo' as scheduled_start_at,
       count(*) filter (where not f.is_scratched and f.horse_number > 0) over (partition by f.race_id, f.held_date) as active_entrant_count
from {{ ref('m_race_entry_feature_matrix') }} f
left join {{ ref('fct_race_basic') }} r on f.race_id=r.race_id
