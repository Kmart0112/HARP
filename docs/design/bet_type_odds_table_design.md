# 券種別オッズテーブル設計メモ

## 0. 目的
単複・馬連・ワイドなど券種ごとに grain が異なるため、オッズ系テーブルは券種別に分離して管理する。

本メモは、以下の 2 つを明確にするための設計メモである。

1. シミュレーション・学習で使う canonical なオッズテーブルの持ち方
2. 当日実行で使う速報オッズ (`s_` 系) の分離方針

## 1. 基本方針

### 1.1 券種ごとに別テーブル
- オッズは券種ごとに別テーブルとする。
- 券種固有の grain と列構造を無理に共通化しない。
- 特に単複と馬連・ワイドは grain が異なるため、同一 fact に混在させない。

### 1.2 canonical テーブルは「最終 odds + 10分前 odds + 払戻」
- シミュレーション・学習用の canonical テーブルは、券種ごとに以下を同居させる。
  - 最終 odds
  - 最終 popularity
  - 発走 10 分前 snapshot odds
  - 発走 10 分前 snapshot popularity
  - 払戻
  - 払戻人気

### 1.3 `s_` 系は別テーブル
- 当日実行を軽くするため、`s_` 系速報 latest は canonical fact に混ぜない。
- `s_` 系は速報専用テーブルとして別に保持する。
- 当日実行では `s_` 系 latest を直接参照する。

## 2. grain

### 2.1 単複
- grain: `race_id + horse_number`

### 2.2 馬連・ワイド
- grain: `race_id + horse_number_1 + horse_number_2`
- 組み合わせは `horse_number_1 < horse_number_2` に正規化する。
- 補助キーとして `pair_key` を持ってよい。
  - 例: `03-11`

## 3. テーブル役割

### 3.1 確定 odds staging
- `stg_n_odds_tanpuku`
- `stg_n_odds_umaren`
- `stg_n_odds_wide`

役割:
- raw から型変換
- `race_id` 生成
- pair 正規化
- odds / popularity の基本列整形

### 3.2 時系列 odds staging
- `stg_n_jodds_tanpuku`
- `stg_n_jodds_umaren`
- `stg_n_jodds_wide`

役割:
- raw 時系列 odds の 1:1 staging
- `happyo_time` の正規化
- pair 正規化

### 3.3 10分前 snapshot fact
- `fct_jodds_snapshot`
- `fct_jodds_umaren_snapshot`
- `fct_jodds_wide_snapshot`

役割:
- 発走時刻 `hassotime` を基準に
  - `happyo_time <= hassotime - interval '10 minutes'`
  を満たす行のうち最新 1 行を採用する

運用:
- heavy model とみなし、通常 DAG から外す
- `published_manual.*` source 経由で downstream 参照する

### 3.4 速報 latest
- `int_s_jodds_latest`
- `int_s_jodds_latest_umaren`
- `int_s_jodds_latest_wide`

役割:
- 当日速報データの最新値を券種別に 1 行へ圧縮する
- 当日実行専用の軽量入力として使う

### 3.5 canonical result fact
- `fct_race_odds_result`
- `fct_race_umaren_odds_result`
- `fct_race_wide_odds_result`

役割:
- 確定 odds
- 10分前 snapshot
- 払戻
を券種別 grain で 1 テーブルにまとめる

注意:
- `s_` 系 latest はここに join しない
- canonical result fact はシミュレーション・学習用とする

## 4. 券種別の推奨列

### 4.1 単複
- `race_id`
- `horse_number`
- `odds_tansho`
- `odds_fukusho_low`
- `odds_fukusho_high`
- `odds_popularity`
- `odds_tansho_10min`
- `odds_fukusho_low_10min`
- `odds_fukusho_high_10min`
- `odds_popularity_10min`
- `pay_tansho`
- `pay_fukusho`

### 4.2 馬連
- `race_id`
- `horse_number_1`
- `horse_number_2`
- `pair_key`
- `odds_umaren`
- `odds_popularity`
- `odds_umaren_10min`
- `odds_popularity_10min`
- `pay_umaren`
- `pay_popularity`

### 4.3 ワイド
- `race_id`
- `horse_number_1`
- `horse_number_2`
- `pair_key`
- `odds_wide_low`
- `odds_wide_high`
- `odds_wide_mid`
- `odds_popularity`
- `odds_wide_low_10min`
- `odds_wide_high_10min`
- `odds_wide_mid_10min`
- `odds_popularity_10min`
- `pay_wide`
- `pay_popularity`

## 5. 利用方針

### 5.1 シミュレーション・学習
- `core.fct_race_*_odds_result` を使う
- 10 分前評価は `*_10min` 列を使う
- 払戻評価は `pay_*` 列を使う

### 5.2 当日実行
- `int_s_jodds_latest_*` を使う
- canonical result fact には依存しない
- 速報を軽量に読むことを優先する

## 6. selector / source 運用
- 10 分前 snapshot は heavy model として通常 selector から外す
- manual selector を券種別に持つ
  - 例: `manual_fct_jodds_snapshot_refresh`
  - 例: `manual_fct_jodds_umaren_snapshot_refresh`
  - 例: `manual_fct_jodds_wide_snapshot_refresh`
- downstream は `published_manual.*` を参照する

## 7. 現時点の決定
- オッズは券種別テーブル
- canonical fact は「最終 odds + 10 分前 odds + 払戻」を持つ
- `s_` 系 latest は canonical fact に混ぜず別テーブル
- 馬連・ワイドは pair grain で正規化する
- 10 分前 snapshot は券種別に manual refresh 運用とする

