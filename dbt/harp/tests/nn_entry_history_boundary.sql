-- Validate the indexed endpoint and both sides of its day-level cutoff.
select e.race_id, e.kettonum
from {{ ref('m_nn_race_entry') }} e
left join {{ ref('int_race_entry_run_record') }} h
  on e.kettonum = h.kettonum and e.history_end_no = h.run_no
left join {{ ref('int_race_entry_run_record') }} next_run
  on e.kettonum = next_run.kettonum and e.history_end_no + 1 = next_run.run_no
where e.history_end_no < 0
   or (e.history_end_no > 0 and (
       h.race_id is null or h.held_date >= e.held_date
       or e.last_history_race_id is distinct from h.race_id
       or e.last_history_held_date is distinct from h.held_date
       or e.days_since_last_run is distinct from e.held_date - h.held_date
   ))
   or (e.history_end_no = 0 and (
       e.last_history_race_id is not null or e.last_history_held_date is not null
       or e.days_since_last_run is not null
   ))
   or next_run.held_date < e.held_date
