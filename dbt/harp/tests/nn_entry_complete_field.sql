-- For every selected race retain ALL active entries, including new horses and
-- missing features. Comparing against the source detects a missing entrant.
with selected_races as (
  select distinct race_id from {{ ref('m_nn_race_entry') }}
), expected as (
  select p.race_id, p.kettonum
  from {{ ref('feat_race_entry_pre_race') }} p
  join selected_races using (race_id)
  where coalesce(p.ijyo_cd, '0') not in ('1', '2', '3') and p.horse_number > 0
), actual as (
  select race_id, kettonum, count(*) as copies, min(active_entrant_count) as declared_count
  from {{ ref('m_nn_race_entry') }}
  group by race_id, kettonum
), expected_counts as (
  select race_id, count(*) as field_count from expected group by race_id
)
select coalesce(e.race_id, a.race_id) as race_id, coalesce(e.kettonum, a.kettonum) as kettonum
from expected e
full join actual a using (race_id, kettonum)
left join expected_counts c on c.race_id = coalesce(e.race_id, a.race_id)
where e.kettonum is null or a.kettonum is null or a.copies <> 1
   or a.declared_count is distinct from c.field_count
