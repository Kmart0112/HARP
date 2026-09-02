# HARP 特徴量検証 UseCase 詳細設計

最終更新: 2026-03-15

## 0. 目的

- 特徴量検証の正式入口を `uv run python -m pipeline.jobs.run_feature_validation` に固定する
- 案件差分は preset YAML で定義し、MLflow を正本として証跡を残す
- validation 実行自体は source registry を変更しない
- 人間による最終 promotion は validation の後段に分離する

## 1. 採用方針

### 1.1 UseCase の分け方

採用方針は「単一 orchestration usecase」である。

- `FeatureValidationUseCase` を 1 本にする
- `scenario` 展開、scenario 用 feature config 解決、scenario run 開始、metrics 実行、必要時 SHAP 実行、レポート生成、MLflow 記録をこの usecase が順序制御する
- MLflow SDK の直接呼び出しはせず、`TrackingPort` を使う
- notebook 実行も `Port` 越しに呼ぶ

### 1.2 実行単位

- `job` は 1 本にする
- Controller は `preset YAML -> Request / Deps` 変換だけを担当する
- `usecase` は「1つの検証案件」を実行する
- 案件差分は `notebook/config/feature_validation_presets/<preset>.yml` に持ち、`Request.scenarios` と `Request.report_spec` に変換する

### 1.3 MLflow run の考え方

- `1 parent run = 1検証案件`
- `1 child run = 1比較シナリオ`
- SHAP が必要な場合も、metrics と同じ scenario child run に同居させる

このため、MLflow UI では `baseline_existing`, `add_A`, `replace_B_with_C` のような scenario 名がそのまま run 一覧として見える。

## 2. 配置

| 層 | 置くもの | 責務 |
|---|---|---|
| `pipeline/jobs` | `run_feature_validation.py` | 引数解釈、結果表示 |
| `controllers` | `FeatureValidationCommand`, deps builder | preset 解決、Request / Deps 組み立て |
| `usecase` | `run_feature_validation_usecase` | 検証案件の手順全体を制御 |
| `interface/ports` | notebook 実行 Port, `TrackingPort` | UseCase から見る I/O 契約 |
| `adapters/driven` | metrics/shap notebook runner, MLflow adapter | subprocess / MLflow / file system 実装 |

## 3. UseCase 境界

### 3.1 Request

`FeatureValidationRequest` は「1つの検証案件」の定義を持つ。

- `validation_name`
- `category`
- `change_summary`
- `experiment_name`
- `features_config_path`
- `feature_sets_path`
- `report_out`
- `runs_csv_out`
- `run_log_dir`
- `command`
- `git_commit`
- `scenarios`
- `report_spec`

### 3.2 Deps

`FeatureValidationDeps` は `usecase` が必要とする Port だけを持つ。

- `file_gateway`
- `tracking_port`
- `metrics_runner_port`
- `shap_runner_port`

補足:

- `file_gateway` は source registry 読み取り、一時 config 書き込み、CSV / report 書き込みに使う
- `metrics_runner_port` / `shap_runner_port` は notebook 実行の I/O 境界
- `usecase` は `subprocess.run` を持たない

### 3.3 Result

`FeatureValidationResult` は job が必要とする出力だけ返す。

- `validation_name`
- `decision`
- `report_path`
- `runs_csv_path`
- `run_log_dir`
- `parent_run_id`
- `scenario_run_ids`
- `scenario_results`
- `restored_features_state`

`restored_features_state` は「source の特徴量定義を触っていない」ことの運用上の確認値として扱う。

## 4. 案件差分を表す DTO

### 4.1 ScenarioSpec

案件ごとの差分は `ValidationScenarioSpec` に集約する。

- `scenario_name`
- `toggles`
- `validation_mode`
- `feature_set_diff`
- `shap_request`

### 4.2 FeatureToggleSpec / FeatureSetDiffSpec

案件差分は 2 方式を併用できる。

- 互換方式: `FeatureToggleSpec`
- 推奨方式: `FeatureSetDiffSpec`

`FeatureSetDiffSpec` は feature registry 上の named feature set を土台に差分だけを指定する。

- `base_feature_set_name`
- `include_features`
- `exclude_features`
- `include_cat_features`
- `exclude_cat_features`

この方式では source registry を書き換えず、scenario ごとの一時 config を生成して metrics notebook に渡す。

### 4.3 ShapReviewSpec

SHAP が必要な scenario だけ `shap_request` を持つ。

- `candidate_feature`
- `comparison_features`
- `validation_mode`
- `report_run_label`

`artifact_path` は metrics runner の結果から決まるため、request 側には持たせない。

### 4.4 ReportSpec

レポート本文に必要な説明は `report_spec` に押し込む。

- `title`
- `background`
- `hypothesis_lines`
- `target_features`
- `leakage_notes`
- `implementation_notes`
- `metrics_notebook_path`
- `shap_notebook_path`

## 5. Port の役割

### 5.1 Metrics notebook 実行 Port

`metrics` 実行は外部 I/O なので Port に切る。

- 入力: `scenario_name`, `run_log_dir`, `features_config_path`
- 出力: `MetricsRunResult`

### 5.2 SHAP notebook 実行 Port

SHAP も同様に Port に切る。

- 入力: `scenario_name`, `artifact_path`, `candidate_feature`, `comparison_features`, `validation_mode`, `metrics_run_label`, `report_run_label`, `delta_auc`, `delta_logloss`, `delta_brier`, `run_log_dir`
- 出力: `ShapReviewResult`

補足:

- `usecase` は notebook の CLI 引数組み立てや stdout / stderr 形式を知らない
- metrics / SHAP の外部コマンド差し替えは driven adapter 側に閉じ込める

## 6. UseCase の責務

`run_feature_validation_usecase(req, deps)` の責務は次に固定する。

1. `Request` の妥当性検証
2. source の特徴量定義と必要な feature set 定義を読み取る
3. parent run を開始し、案件メタデータを記録する
4. scenario ごとに child run を開始し、一時 feature config を生成する
5. metrics 実行を制御する
6. SHAP 対象 scenario では同じ child run の中で SHAP 実行も制御する
7. 比較結果から最終判定を組み立てる
8. runs CSV と最終レポートを出力し、parent run に保存する
9. child / parent run を `FINISHED` / `FAILED` で close する

## 7. UseCase の非責務

- `subprocess.run` の実行
- MLflow SDK の直接 import
- artifact の実保存方式
- notebook の UI / marimo 実装詳細
- dbt 実行や feature 生成ロジック本体
- `pipeline/config/feature_registry.yml` への promotion
- legacy feature-set artifact の同期

promotion と feature registry 更新は validation job の外で人間が行う。

## 8. 実行シーケンス

### 8.1 正常系

標準シーケンスは次の通り。

1. request を検証する
2. parent run を開始する
3. parent run に params / tags / 入力 snapshot を記録する
4. baseline scenario を child run として実行する
5. 各 scenario ごとに一時 `features_*.yml` を生成する
6. `metrics_runner_port.run_metrics()` を呼ぶ
7. baseline との差分 `delta` を計算する
8. SHAP 対象なら `shap_runner_port.run_shap_review()` を呼ぶ
9. scenario child run に params / metrics / log / artifact / summary JSON を記録する
10. runs CSV を書く
11. 最終レポート Markdown を書く
12. parent run に report / CSV / summary JSON を記録する
13. parent run に `decision` tag を付けて close する
14. `FeatureValidationResult` を返す

### 8.2 失敗系

失敗時の責務も usecase が持つ。

1. 開始済み scenario child run は `FAILED` で terminate する
2. parent run は `FAILED` で terminate する
3. source registry は validation 実行で書き換えていない前提を保つ
4. 失敗を握り潰さず、job まで例外を伝播する

## 9. MLflow の実行ポイント

### 9.1 parent run

- 開始点: scenario 実行前
- 記録するもの:
  - params: `validation_name`, `category`, `change_summary`, `features_config_path`, `command`
  - tags: `git_commit`, `report_path`, `runs_csv_path`
  - artifact: 入力 config snapshot や summary
- close 点: 最終レポートと summary JSON の記録後

### 9.2 scenario child run

- 開始点: 各 scenario の実行直前
- 記録するもの:
  - params: `scenario_name`, `validation_mode`, `enabled_features`
  - tags: `run_role=scenario`, `has_shap`, `candidate_feature` など
  - metrics: `auc`, `logloss`, `brier`, `delta_auc`, `delta_logloss`, `delta_brier`
  - artifacts: 一時 feature config、metrics log、model artifact、manifest、scenario summary JSON
  - 必要時 artifacts: SHAP markdown、関連 log や summary
- close 点: その scenario の metrics と必要時 SHAP の記録完了後

補足:

- baseline も独立した child run にする
- `add A`, `add B`, `add A+B` の比較は child run の一覧として MLflow UI 上で並ぶ
- SHAP が必要な場合も artifact は同じ scenario child run に同居させる

## 10. レポート生成の扱い

### 10.1 方針

レポート生成は UseCase 内の pure helper で行う。

理由:

- レポート本文は外部 I/O ではなく、検証結果の業務的な組み立てである
- ファイル保存だけ `FileGatewayPort` を使えばよい
- 今回は template engine を増やすより、まず固定構造の Markdown 生成で十分である

### 10.2 レポート本文に必ず入れる項目

- `mlflow_experiment_name`
- `mlflow_run_id`
- scenario 比較表
- SHAP 要約
- 最終判定
- 一時 config で validation したこと
- `採用` 時は feature registry へ手動反映する運用

`feature_validation_log.csv` への追記は新フローでは行わない。

## 11. 運用との接続

validation job の後段運用は次に固定する。

1. MLflow parent run と最終レポートで evidence を確認する
2. `採用` の場合だけ `pipeline/config/feature_registry.yml` を更新する
3. 必要なら render utility で対象 feature set の出力を確認する

これにより、validation 実行は非破壊のまま保ち、日常運用の active set と `feature_set` preset の土台 registry 定義を一致させる。

## 12. 受け入れ条件

- `uv run python -m pipeline.jobs.run_feature_validation` から 1 案件を実行できる
- MLflow に `1 parent + scenario 数ぶんの child run` が作成される
- child run 一覧を見れば `baseline`, `add A`, `replace B with C` の比較単位が分かる
- report / runs CSV / SHAP artifact が parent run と scenario child run から追跡できる
- source registry は validation 実行で変更されない
- report が「推奨反映内容」と「MLflow evidence」を明示する

## 13. 採らない案

### 13.1 metrics child run と shap child run を分ける

採らない。

理由:

- `add A` の metrics と SHAP を別 run にすると、比較単位と run 粒度がずれる
- MLflow UI で見たいのは artifact 種別ではなく scenario 単位である

### 13.2 job 側で scenario を回す

採らない。

理由:

- `pipeline/jobs` に業務手順が漏れる
- 失敗時の復元責務が分散する
- hexagonal の責務分離と合わない

### 13.3 validation 中に source registry を直接更新する

採らない。

理由:

- 実験条件が file state に埋もれる
- rerun と比較がしづらい
- MLflow の child run ごとの条件を artifact として残しにくい
