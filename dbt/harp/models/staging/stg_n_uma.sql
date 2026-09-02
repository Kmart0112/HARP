{{config( 
    materialized='table',
    description='Staging table for horse data from N_UMA source table.'
) }}

select
    *,
    kettonum ::bigint as kettonum_int,
    case
        when Ketto3InfoBamei1 = 'ロードカナロア' then 1
        when Ketto3InfoBamei1 = 'キズナ' then 2
        when Ketto3InfoBamei1 = 'エピファネイア' then 3
        when Ketto3InfoBamei1 = 'モーリス' then 4
        when Ketto3InfoBamei1 = 'キタサンブラック' then 5
        when Ketto3InfoBamei1 = 'ルーラーシップ' then 6
        when Ketto3InfoBamei1 = 'パイロ' then 7
        when Ketto3InfoBamei1 = 'ホッコータルマエ' then 8
        when Ketto3InfoBamei1 = 'オルフェーヴル' then 9
        when Ketto3InfoBamei1 = 'ハービンジャー' then 10
        when Ketto3InfoBamei1 = 'リオンディーズ' then 11
        when Ketto3InfoBamei1 = 'ヘニーヒューズ' then 12
        when Ketto3InfoBamei1 = 'ドゥラメンテ' then 13
        when Ketto3InfoBamei1 = 'ドレフォン' then 14
        when Ketto3InfoBamei1 = 'シルバーステート' then 15
        when Ketto3InfoBamei1 = 'ゴールドシップ' then 16
        when Ketto3InfoBamei1 = 'リアルスティール' then 17
        when Ketto3InfoBamei1 = 'シニスターミニスター' then 18
        when Ketto3InfoBamei1 = 'ミッキーアイル' then 19
        else 0
    end as sire_cat,
    case 
        when breedername = 'ノーザンファーム' then 1
        when breedername = '社台ファーム' then 2
        when breedername = '社台コーポレーション白老ファーム' then 3
        when breedername = '下河辺牧場' then 4
        when breedername = '三嶋牧場' then 5
        when breedername = '岡田スタッド' then 6
        when breedername = '千代田牧場' then 7
        when breedername = '追分ファーム' then 8
        when breedername = 'ケイアイファーム' then 9
        when breedername = 'ビッグレッドファーム' then 10
        when breedername = 'ノースヒルズ' then 11
        else 0
    end as breeder_cat,
    BreederCode ::int as breeder_cd,

    case
        when chokyosiryakusyo in ('矢作芳人', '矢作博人') then 1
        when chokyosiryakusyo = '杉山晴紀' then 2
        when chokyosiryakusyo = '斉藤崇史' then 3
        when chokyosiryakusyo = '藤沢和雄' then 4
        when chokyosiryakusyo = '友道康夫' then 5
        when chokyosiryakusyo = '木村哲也' then 6
        when chokyosiryakusyo = '堀宣行' then 7
        when chokyosiryakusyo = '中内田充正' then 8
        when chokyosiryakusyo = '須貝尚介' then 9
        when chokyosiryakusyo = '清水久詞 ' then 10
        when chokyosiryakusyo = '上村洋行' then 11
        when chokyosiryakusyo = '池江泰寿' then 12
        else 0
    end as trainer_cat,
    
    -- EveryDB2 UMA pedigree slots: 1=sire, 2=dam, 5=damsire.
    Ketto3InfoHansyokuNum1 ::bigint as sire_id,
    Ketto3InfoBamei1 as sire_name,
    Ketto3InfoHansyokuNum2 ::bigint as dam_id,
    Ketto3InfoHansyokuNum5 ::bigint as damsire_id,
    to_date(BirthDate, 'YYYYMMDD') as birth_date

from {{ source('raw', 'n_uma') }}
