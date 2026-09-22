{{ config(materialized='view', tags=['odds_contract_v1']) }}
-- Retain missing outcomes/odds so the application can report exclusion coverage.
select f.*, o.result_order, o.is_win, o.is_place
from {{ ref('m_race_inputs_v1') }} f
left join {{ ref('int_race_entry_outcome') }} o
  on f.race_id=o.race_id and f.kettonum=o.kettonum

