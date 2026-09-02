create table if not exists races (
  race_id bigint primary key,
  held_date date not null,
  jyo_cd text not null,
  kaiji int not null,
  nichiji int not null,
  race_num int not null,

  name text not null,
  distance_m int,
  track_cd text,

  source text not null default 'everydb2',
  updated_at timestamptz not null default now()
);

create index if not exists idx_races_held_date on races(held_date);
create index if not exists idx_races_jyo_date on races(jyo_cd, held_date);