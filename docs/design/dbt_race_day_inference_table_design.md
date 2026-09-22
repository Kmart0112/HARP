# 学習・当日推論テーブルの現行契約

Python runtimeの現在の公開境界は [odds_input_contract.md](odds_input_contract.md) を参照。本書のtrain/predict martは互換経路として保持し、通常のPortはodds-free入力と日時付きquoteを別々に束ねて読む。

実行手順は [dbt_race_day_inference_strategy.md](dbt_race_day_inference_strategy.md) を参照する。
本書は現行SQLに沿った粒度・入力・出口の契約を扱う。

## 基礎情報

| モデル | 粒度 | 役割 |
|---|---|---|
| `fct_race_basic` | `race_id` | 蓄積系レース情報から事前のレース・コース情報を作る |
| `fct_race_entry_declared` | `race_id, kettonum` | 結果なしの馬も含む出馬情報。`stg_n_uma_race_all` と馬マスタを使う |
| `fct_race_entry_result` | `race_id, kettonum` | 馬単位の結果。複勝ラベルの頭数判定は現在 `fct_race` に依存 |
| `fct_race_result` | `race_id` | レース単位の確定結果。旧 `fct_race` の全利用側を置換した状態ではない |
| `int_race_entry_spine` | `race_id, kettonum` | 出馬情報と結果有無から `entry_status` / `is_prediction_target` を作る |
| `int_race_entry_outcome` | `race_id, kettonum` | 学習出口に渡す結果・教師ラベル |

速報出馬情報だけではspineは作られない。対象日の出走馬が蓄積系 `n_uma_race` に投入されていることが前提。

## 特徴量contextと共通matrix

| モデル | 粒度 | 直接入力 |
|---|---|---|
| `int_race_entry_feature_context` | `race_id, kettonum` | spine、declared、race_basic |
| `int_race_day_feature_context` | `race_id, kettonum` | spine、declared、race_basic、`stg_s_uma_race` |
| `m_race_entry_feature_matrix` | `race_id, kettonum` | modeに応じたcontext、履歴lookup、調教・DM情報 |

学習contextは速報を読まず、当日contextは `target_held_date` に絞る。
当日contextは `stg_s_uma_race` の同一馬を `datakubun` 降順で1行にし、
馬体重・馬体重増減・取消状態を優先して反映する。
天候・馬場・頭数は現行SQLではrace_basic側の値を使う。

contextで体重bin・年齢・斤量補正・遠征区分・馬番比率などを計算し、
matrixで履歴lookupやレース内相対特徴量を結合する。
現レースの結果とオッズ・人気・snapshot列はmatrixに入れない。

### 入力mode

- `training`：学習contextを使う。既定値。
- `latest`：対象日の当日contextを使う。
- `all`：対象日は当日context、それ以外は学習contextを使う。

`feature_input_mode` を指定する。旧 `feature_snapshot_mode` は未移行の呼出元向けfallback。
modeは入力の選択であり、matrixにsnapshot別の行を増やす指定ではない。

### 更新範囲

matrixは `race_id, kettonum` をunique keyとするincrementalモデル。
学習入力は明示された対象日・期間を優先し、未指定のincremental実行では直近7日を対象とする。
当日入力は対象日のみ。履歴lookupは作成済みの内容を参照する。

## オッズ

| モデル | 粒度 | 役割 |
|---|---|---|
| `int_race_day_odds_history` | `race_id, horse_number, snapshot_time_key` | 対象日の速報 `stg_s_jodds_tanpuku` を正規化 |
| `int_race_day_odds_latest` | `race_id, horse_number` | historyから `snapshot_time_key` 最大の行を採用 |
| `int_race_entry_odds_snapshot` | `race_id, horse_number, odds_snapshot_type` | 学習用の `pre10m` オッズ |
| `fct_race_entry_final_odds` | `race_id, horse_number` | 確定オッズの独立した参照先 |

historyとlatestは `table` materializationで、対象日の速報を読み直す。
名前がhistoryでも、日付をまたいで全snapshotを永続追記するモデルではない。
最新値の `odds_source` は `int_race_day_odds_history`。

学習snapshotは `published_manual.fct_jodds_snapshot` sourceを参照する。
重いsnapshotモデルは通常のDAGでは再計算せず、専用manual selectorで更新する。

## 学習・推論の出口

### `m_train_race_entry_features`

粒度は `race_id, kettonum, odds_snapshot_type`。snapshotは `pre10m` に限定する。

1. matrixから取消馬を除外する。
2. `race_id, horse_number` でpre10mオッズを内部結合する。
3. `race_id, kettonum` でoutcomeを内部結合する。
4. `result_order` / `is_win` / `is_place` を付与する。

学習出口のincremental更新は、指定日・期間を優先し、未指定時は直近7日を対象にする。

### `m_predict_race_entry_features`

粒度は `race_id, kettonum`。対象日の出走馬と `latest` オッズを扱うtable。

1. matrixを対象日に絞り、取消馬を除外する。
2. `race_id, horse_number` で最新オッズを左結合する。
3. 欠損オッズの馬も残し、`odds_source = missing_live_odds` とする。

両出口はオッズ・人気・複勝オッズ平均と、`log_odds_tansho` / `popularity_ratio` を付与する。
`j_odds_tansho` は `odds_tansho` の互換列名として残す。
PythonのEV計算は別のrepository呼出しでオッズを取得する現行実装なので、
この推論martを作るだけでPython側の全参照が新ルートへ移るわけではない。

## 検証契約

- matrixの `race_id, kettonum` が重複しない。
- matrixにオッズ・人気・snapshot列が混入しない。
- 学習snapshotは `pre10m`、推論snapshotは `latest`。
- 最新オッズはhistory由来で、レース・馬ごとに一意。

契約テストは `dbt/harp/tests/` に置く。SQL/YAML変更時はparse、selector確認、
必要な対象モデルのbuild・data testを実施する。実値envはGit管理しない。
