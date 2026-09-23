-- A corrupt sequence makes array slicing address the wrong historical race.
with ordered as (
  select kettonum, race_id, held_date, run_no,
    lag(run_no) over (partition by kettonum order by held_date, race_id) as previous_no
  from {{ ref('int_race_entry_run_record') }}
)
select kettonum, race_id
from ordered
where run_no <> coalesce(previous_no, 0) + 1
union all
select kettonum, race_id
from {{ ref('int_race_entry_run_record') }}
group by kettonum, race_id
having count(*) <> 1
