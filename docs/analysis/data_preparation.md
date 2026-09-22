# 分析データ作成

## 目的

分析の最初の責務は、PostgreSQL 上の競馬データを、学習・推論・検証で使いやすい粒度へ整えること。HARP ではこの責務を主に `dbt/harp` に置く。

## dbt レイヤ

- `staging`: 元テーブルの型、命名、最低限の正規化
- `intermediate`: レース、出走馬、調教、オッズなどの中間集計
- `core`: canonical な fact/dimension 相当のモデル
- `features`: 再利用可能な特徴量モデル
- `mart`: 学習・推論・レポートで直接使う最終テーブル

学習出口は `m_train_race_entry_features`、当日推論出口は `m_predict_race_entry_features`。
両者はオッズを含まない `m_race_entry_feature_matrix` を共有し、出口でオッズを結合する。
Python runtimeが使用中の `m_train_race_horse_past5` は互換入口として残している。

## 標準フロー

1. source/staging で生データを安定した列定義へ寄せる。
2. intermediate/core でレース・出走馬・調教・オッズの結合粒度をそろえる。
3. features で特徴量を追加する。
4. mart で学習や検証に使うテーブルへ集約する。
5. notebook や job から mart を読み、モデル検証へ進む。

dbt の実行方法は [../../dbt/harp/README.md](../../dbt/harp/README.md) を参照する。

## リーク防止

特徴量は「予測時点で利用できる情報か」を基準に分ける。レース後にしか分からない情報、確定払戻、結果由来の列は、学習ターゲットや評価には使っても推論特徴量には混ぜない。

レース当日推論のテーブル分離は [../design/dbt_race_day_inference_strategy.md](../design/dbt_race_day_inference_strategy.md) と [../design/dbt_race_day_inference_table_design.md](../design/dbt_race_day_inference_table_design.md) を参照する。
