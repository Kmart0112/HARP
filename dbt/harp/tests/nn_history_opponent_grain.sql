with expected as (
  select race_id, kettonum, held_date, run_no,
    count(*) over (partition by race_id) - 1 as opp_count
  from {{ ref('int_race_entry_run_record') }}
), actual as (
  select race_id, kettonum, count(*) as copies, min(held_date) as held_date,
    min(run_no) as run_no, min(opp_count) as opp_count
  from {{ ref('m_nn_run_history') }}
  group by race_id, kettonum
)
select coalesce(e.race_id, a.race_id) as race_id, coalesce(e.kettonum, a.kettonum) as kettonum
from expected e
full join actual a using (race_id, kettonum)
where e.kettonum is null or a.kettonum is null or a.copies <> 1
   or e.held_date is distinct from a.held_date
   or e.run_no is distinct from a.run_no
   or e.opp_count is distinct from a.opp_count
