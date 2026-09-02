# 特徴量定義・検証統合レポート（テンプレート）

このテンプレートは、1回の実行で行った「特徴量定義」と「検証結果」を1つのレポートにまとめるための雛形です。  
保存先は `notebook/report/features` を想定します。`notebook/report/results` はログ置き場として扱います。

## 0. 実行情報
- 実行日: YYYY-MM-DD
- 担当:
- 実行名: （何を変えた実行か）
- 区分: （candidate_addition / existing_comparison など）
- 関連チケット・PR:
- 評価ノートブック: `notebook/prd/lgbm_fuku_platt_metrics.py`

## 1. 目的
- 背景:
- 仮説:
- 今回の変更対象（特徴量/特徴量セット）:

## 2. リークチェック（事前確認）
- as-of（値が確定する時点）:
- 対象レースの結果情報（rank/払戻/確定後指標）不使用の確認:
- 将来情報不使用の確認:
- 補足:

## 3. 変更一覧（特徴量定義サマリ）
| 特徴量名 | 種別 | 変更種別 | 作り方/意味の1行要約 | 判定 |
|---|---|---|---|---|
| feature_a | num/cat/cluster | add/update/drop |  | 採用/保留/不採用 |
| feature_b | num/cat/cluster | add/update/drop |  | 採用/保留/不採用 |

## 4. 特徴量詳細（必要な数だけ繰り返し）
### 4.1 `<feature_name>`
- 作り方: （利用テーブル・主要カラム・式・集計窓）
- 意味: （何を表し、なぜ効く想定か）
- 実装反映先:
  - dbtモデル:
  - model YAML（description記載先）:
  - 最終列: `mart.m_train_race_horse_past5.<column_name>`
  - `pipeline/config/feature_registry.yml` の反映位置:
- リーク再確認:

### 4.2 `<feature_name>`
- 作り方:
- 意味:
- 実装反映先:
- リーク再確認:

## 5. 実行条件
- DB変更有無: あり / なし
- dbt実行コマンド（必要時）:
  - `uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1 dbt build -f --selector training_default`
- 評価コマンド:
  - `HARP_DB_URL=<postgres_url> uv run python notebook/prd/lgbm_fuku_platt_metrics.py`
- キャッシュクリア有無: あり / なし
- 実験結果CSV:
- 実行ログ:

## 6. 検証結果
### 6.1 ベースライン
| run | AUC | LogLoss | Brier |
|---|---:|---:|---:|
| baseline |  |  |  |

### 6.2 単体アブレーション
（`DeltaAUC = run - baseline`, `DeltaLogLoss = run - baseline`）

| run | AUC | LogLoss | Brier | DeltaAUC | DeltaLogLoss | DeltaBrier | 判定 |
|---|---:|---:|---:|---:|---:|---:|---|
| + feature_a |  |  |  |  |  |  | 採用/保留/不採用 |
| + feature_b |  |  |  |  |  |  | 採用/保留/不採用 |

### 6.3 重複比較 / バリアント比較（該当時）
| scenario | group_id | tested_set | AUC | LogLoss | Brier | DeltaAUC | DeltaLogLoss | 判定 |
|---|---|---|---:|---:|---:|---:|---:|---|
| aggregate_only/source_only/all_features/variant_compare |  |  |  |  |  |  |  |  |

### 6.4 最終確認ラン
| run | AUC | LogLoss | Brier | DeltaAUC | DeltaLogLoss | DeltaBrier |
|---|---:|---:|---:|---:|---:|---:|
| final_candidate |  |  |  |  |  |  |

### 6.5 SHAP レビュー（`candidate_addition` では必須 / `existing_comparison` では任意）
- 実行 notebook: `notebook/lab/lgbm_fuku_platt_shap.py`
- candidate feature:
- comparison features:
- metrics_judgement: `improved / mixed / not_improved`
- shap_judgement: `問題なし / 要注意 / 懸念あり`
- candidate global importance:
  - global rank:
  - mean_abs_shap:
  - importance_share:
- candidate dependence:
  - `![Candidate dependence: <feature_name>](_images/<report_stem>_<feature_name>_dependence.png)`
- dependence の形の考察:
  - （手動記入）単調性 / 閾値 / 飽和 / U字 / 外れ値依存の有無を確認して追記
- local explanation 所見:
- redundancy コメント:
- stability コメント:
- leakage suspicion:
- metrics 未改善時の SHAP 補足:
- shap_report_path: `notebook/report/shap/YYYYMMDD_<run_label>_shap_report.md`

## 7. 最終判定
- 判定: 採用 / 保留 / 不採用
- 判定理由:
  - metrics 判定:
  - AUC:
  - LogLoss:
  - Brier（任意）:
  - shap 判定:
  - 総合コメント:
- 採用セット（最終）:
- 不採用/保留の扱い:

## 8. 反映内容
- `pipeline/config/feature_registry.yml`:
  - ON (`set_status.status: on`):
  - OFF（対象 set の `set_status` を削除 / 未記載にする）:
- 追加/更新した主なファイル:
  - `dbt/harp/models/...`
  - `pipeline/config/feature_registry.yml`

## 9. MLflow 紐付け情報
- mlflow_experiment_name:
- mlflow_run_id:
- parent summary artifact:
- child metrics / shap artifacts:
- 実行コマンド:
  - `uv run python -m pipeline.jobs.run_feature_validation --preset <preset_name>`

補足:
- 新規の正式運用では、このレポートと parent run の `mlflow_run_id` を根拠に判断する。
- `feature_validation_log.csv` は legacy history として残すだけで、新規の正式運用では追記しない。

## 10. 補足メモ（任意）
- 次回の検証候補:
- 残課題:
