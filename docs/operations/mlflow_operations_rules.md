# HARP MLflow 運用ルール

最終更新: 2026-03-14

## 0. 目的
- HARP における実験・評価・検証の証跡を、原則 MLflow に集約する。
- workflow が未整備でも、最低限同じ run ルールで記録できるようにする。
- Git には最終判断だけを残し、詳細証跡は MLflow で追える状態を標準にする。

本書は「実装案」ではなく、日々の運用で従うルールを定義する。

## 1. 基本原則
- MLflow は「実行証跡の正本」とする。
- Git は「最終判断と要約レポートの正本」とする。
- 何かを採用・保留・不採用と判断したら、その根拠 run を `mlflow_run_id` で辿れるようにする。
- workflow が未整備でも、実験を行ったら可能な限り MLflow run を作る。
- notebook 単発実行や手元検証でも、再現したいものは MLflow に残す。

## 2. 対象範囲

### 2.1 すぐに対象にするもの
- 特徴量検証
- 既存特徴量整理
- モデル学習・再学習
- calibration 評価
- betting / backtest 評価
- 仮説検証用の ad hoc 実験

### 2.2 例外
- 一時メモや読み捨て探索
- 実行途中で中断し、判断材料にもならないもの

ただし、少しでも再利用や比較の可能性があるなら MLflow に残す方を優先する。

## 3. 実験単位

### 3.1 原則
- `1 parent run = 1つの意思決定テーマ`
- `1 child run = 1つの比較責務または実行責務`

「1コマンド = 1 run」ではなく、「1つの判断テーマ = 1 parent run」で切る。

### 3.2 代表例
| テーマ | parent run | child run |
|---|---|---|
| 新規特徴量検証 | 1特徴量案または1変更テーマ | baseline / single_add / feature_set_add / replace_existing |
| 既存特徴量整理 | 1 keep-drop テーマ | existing_only / variant_a / variant_b / keep_both |
| モデル更新 | 1モデル版の採否判断 | train / calibrate / evaluate |
| betting 検証 | 1戦略案の採否判断 | predict / backtest / sensitivity |
| ad hoc 実験 | 1仮説 | 実行パターンごとの差分 run |

### 3.3 いま正式 workflow があるもの
- 特徴量検証は `uv run python -m pipeline.jobs.run_feature_validation` を正式入口とする。
- 既存特徴量整理は `uv run python -m pipeline.jobs.run_feature_selection` を正式入口とする。

### 3.4 まだ workflow がないもの
- workflow 未整備でも、まずは手動または簡易スクリプトで MLflow run を作る。
- その際も experiment 名、run 名、params / tags / artifacts の付け方は本書に従う。

## 4. Experiment 名
- experiment は案件名ではなく運用カテゴリで切る。
- 原則として次を使う。

| experiment_name | 用途 |
|---|---|
| `feature_validation` | 新規特徴量の採否判断 |
| `feature_selection` | 既存特徴量の keep / drop、variant 整理 |
| `model_training` | モデル学習、再学習、学習条件比較 |
| `model_evaluation` | calibration、追加評価、安定性確認 |
| `betting_evaluation` | 予測結果を使った戦略評価 |
| `adhoc_research` | workflow 未整備の探索・仮説検証 |

新しい experiment を増やすのは、本当にカテゴリが違うときだけにする。

## 5. Run 名

### 5.1 parent run 名
- 人が見てテーマを判断できる短い名前にする。
- 例:
  - `raw_course_features`
  - `pos4_agari_variant_selection`
  - `place_platt_v2_training`
  - `fuku_ev_threshold_0_12`

### 5.2 child run 名
- 比較責務が分かる名前にする。
- 例:
  - `baseline_existing`
  - `add_turn_direction_raw`
  - `replace_course_history_with_raw`
  - `train_seed_42`
  - `evaluate_2025_holdout`
  - `backtest_2024Q4`

## 6. 最低限残す metadata

### 6.1 parent run params
- `theme`
- `target`
- `command`
- `git_commit`
- `data_snapshot`
- `feature_registry` または `feature_set`
- `split_policy`

### 6.2 parent run tags
- `category`
- `decision`
- `owner`
- `report_path`

### 6.3 child run params
- `scenario_name` または `step_name`
- `feature_set`
- `train_year_start`
- `train_year_end`
- `test_year`
- `seed`

### 6.4 child run metrics
- 指標だけを入れる。
- 例:
  - `auc`
  - `logloss`
  - `brier`
  - `calibration_error`
  - `roi`
  - `hit_rate`

差分値は metrics に入れてもよいが、比較表は artifact 側にも残す。

## 7. Artifact ルール

### 7.1 MLflow に残すもの
- 実行ログ
- metrics 要約 JSON / CSV
- model artifact
- manifest
- SHAP レポートと図
- prediction / backtest の中間出力
- 実験条件を再現する設定ファイル

### 7.2 Git に残すもの
- 最終レポート
- feature / model / betting card
- 採否判断
- `mlflow_run_id`

### 7.3 Git に残さないもの
- 重い artifact
- 毎回増える中間 CSV
- SHAP の画像一式
- 生の stdout / stderr

## 8. レポートとの紐付け
- 最終レポートには必ず parent run の `mlflow_experiment_name` と `mlflow_run_id` を書く。
- Git に残す根拠 ID は parent run のみとする。
- child run の比較は MLflow UI 側で追う。
- `feature_card` / `model_card` / `betting_card` の evidence は `evidence_mlflow_run_id` に寄せる。

## 9. rerun / 失敗時の扱い

### 9.1 rerun
- 同じ判断テーマで一部 scenario だけ再実行する場合は、原則として既存 parent run に append する。
- append は `theme_status=open` の parent run に対してだけ許可する。
- parent run の report / summary / CSV は append のたびに再生成する。
- そのテーマを閉じたあとに別仮説としてやり直す場合だけ、新しい parent run を切る。

### 9.2 failed run
- failed run は削除しない。
- 原因切り分けが済むまで保持する。
- 失敗をやり直した場合も、元 run は残す。

## 10. workflow ごとの当面ルール

### 10.1 特徴量検証
- 正式入口は `uv run python -m pipeline.jobs.run_feature_validation`
- experiment は `feature_validation`
- run 構成は `1 parent + scenario child runs`
- source registry は編集しない
- 標準フローは `baseline -> candidate単独 single_add -> 改善セット feature_set_add append -> finalize/promotion`
- ただし当面は、エージェントは `finalize` を実行せず、theme の終了は人が CLI から行う
- SHAP は新規追加特徴量では必須とし、scenario child run の中で実行し、独立 child run にはしない
- 関連のある新規特徴量を複数追加した場合は、関連セットを同時に有効化した SHAP scenario で dependence を確認する

### 10.2 既存特徴量整理
- experiment は `feature_selection`
- `uv run python -m pipeline.jobs.run_feature_selection` を正式入口とし、既存 ON 特徴量の keep / drop 専用フローとして扱う
- candidate 追加の続きとして混ぜず、別テーマとして運用する

### 10.3 モデル学習
- experiment は `model_training`
- 学習、calibration、最終評価を分けるなら child run で切る
- 最終判断は parent run に集約する

### 10.4 betting 評価
- experiment は `betting_evaluation`
- prediction と backtest を child run に分けてよい
- 戦略パラメータは params に残す

### 10.5 ad hoc 実験
- experiment は `adhoc_research`
- 後で判断材料になるなら、雑でも MLflow に残す
- その後、繰り返し使うものだけ正式 workflow 化する

## 11. 実装上の原則
- `pipeline/jobs -> controllers -> usecase` の依存方向を守る。
- MLflow SDK の直接 import は `adapters/driven` に閉じ込める。
- usecase は MLflow 実装を知らず、Port 経由で扱う。
- notebook や script を呼ぶ処理も runner Port 越しに行う。

## 12. 当面の導入順
1. 特徴量検証を正式フローとして運用する
2. 既存特徴量整理を `feature_selection` として MLflow 管理へ寄せる
3. モデル学習の parent/child run ルールを整える
4. betting 評価を同じ運用ルールに揃える
5. ad hoc 実験は `adhoc_research` で先に吸収する

## 13. 迷ったときの判断
- Git に全部残したくなったら: まず MLflow に寄せる
- run の切り方で迷ったら: 「最終判断が1本にまとまる単位」で parent を切る
- experiment 名で迷ったら: 既存カテゴリに寄せる
- workflow が未整備でも: 先に MLflow に残す

このルールの狙いは、完璧な自動化より先に「判断の証跡を散らさない」ことである。
