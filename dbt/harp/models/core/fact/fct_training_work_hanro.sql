with ranked_day as (
    select
        wc.kettonum,
        wc.chokyo_date,
        wc.chokyo_time,
        wc.tozai_cd,
        wc.lap_time_1,
        wc.lap_time_2,
        wc.lap_time_3,
        wc.lap_time_4,
        wc.haron_time_4,
        {{ training_accel_flag([
            'wc.lap_time_1',
            'wc.lap_time_2',
            'wc.lap_time_3',
            'wc.lap_time_4',
        ]) }} as accel_flag,
        row_number() over (
            partition by wc.kettonum, wc.chokyo_date
            order by wc.lap_time_1 asc, wc.chokyo_time desc
        ) as rn
    from {{ ref('stg_n_hanro') }} wc
    where wc.lap_time_1 < 13
      and wc.haron_time_4 < 57
),

train_day as (
    select
        kettonum,
        chokyo_date,
        tozai_cd,
        lap_time_1,
        lap_time_2,
        haron_time_4,
        accel_flag
    from ranked_day
    where rn = 1
),

ranked_day_z_pool as (
    select
        wc.kettonum,
        wc.chokyo_date,
        wc.chokyo_time,
        wc.tozai_cd,
        wc.lap_time_1,
        wc.haron_time_4,
        row_number() over (
            partition by wc.kettonum, wc.chokyo_date
            order by wc.lap_time_1 asc, wc.chokyo_time desc
        ) as rn
    from {{ ref('stg_n_hanro') }} wc
    where wc.lap_time_1 <= 14
),

train_day_z_pool as (
    select
        kettonum,
        chokyo_date,
        tozai_cd,
        lap_time_1,
        haron_time_4
    from ranked_day_z_pool
    where rn = 1
),

peer_stats as (
    select
        tozai_cd,
        chokyo_date,
        count(*) as peer_n_tozai_day,
        avg(lap_time_1) as lap_time_1_mean_tozai_day,
        stddev_samp(lap_time_1) as lap_time_1_std_tozai_day,
        avg(haron_time_4) as haron_time_4_mean_tozai_day,
        stddev_samp(haron_time_4) as haron_time_4_std_tozai_day
    from train_day_z_pool
    group by 1, 2
),

feat as (
    select
        td.kettonum,
        td.chokyo_date,
        td.tozai_cd,
        td.lap_time_1,
        td.lap_time_2,
        td.haron_time_4,
        td.accel_flag,
        ps.peer_n_tozai_day,
        ps.lap_time_1_mean_tozai_day,
        ps.lap_time_1_std_tozai_day,
        ps.haron_time_4_mean_tozai_day,
        ps.haron_time_4_std_tozai_day,
        avg(td.lap_time_1) over (
            partition by td.kettonum
            order by td.chokyo_date
            rows between unbounded preceding and 1 preceding
        ) as lap_time_1_avg,
        min(td.lap_time_1) over (
            partition by td.kettonum
            order by td.chokyo_date
            rows between unbounded preceding and 1 preceding
        ) as lap_time_1_min,
        avg(td.haron_time_4) over (
            partition by td.kettonum
            order by td.chokyo_date
            rows between unbounded preceding and 1 preceding
        ) as haron_time_4_avg,
        min(td.haron_time_4) over (
            partition by td.kettonum
            order by td.chokyo_date
            rows between unbounded preceding and 1 preceding
        ) as haron_time_4_min
    from train_day td
    left join peer_stats ps
        on td.tozai_cd = ps.tozai_cd
        and td.chokyo_date = ps.chokyo_date
)

select
    f.kettonum,
    f.chokyo_date,
    f.tozai_cd,
    f.lap_time_1,
    f.lap_time_2,
    f.haron_time_4,
    f.accel_flag,
    f.peer_n_tozai_day,
    f.lap_time_1_mean_tozai_day,
    f.lap_time_1_std_tozai_day,
    case
        when f.lap_time_1 is null or f.lap_time_1_std_tozai_day is null or f.lap_time_1_std_tozai_day = 0 then null
        else (f.lap_time_1 - f.lap_time_1_mean_tozai_day) / f.lap_time_1_std_tozai_day
    end as lap_time_1_z_tozai_day,
    f.haron_time_4_mean_tozai_day,
    f.haron_time_4_std_tozai_day,
    case
        when f.haron_time_4 is null or f.haron_time_4_std_tozai_day is null or f.haron_time_4_std_tozai_day = 0 then null
        else (f.haron_time_4 - f.haron_time_4_mean_tozai_day) / f.haron_time_4_std_tozai_day
    end as haron_time_4_z_tozai_day,
    f.lap_time_1 - f.lap_time_1_avg as lap_time_1_diff_avg,
    f.lap_time_1 - f.lap_time_1_min as lap_time_1_diff_min,
    f.haron_time_4 - f.haron_time_4_avg as haron_time_4_diff_avg,
    f.haron_time_4 - f.haron_time_4_min as haron_time_4_diff_min,
    f.haron_time_4_min,
    f.lap_time_1_min
from feat f
