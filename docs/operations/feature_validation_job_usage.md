# Feature Validation Job 使い方

`pipeline.jobs.run_feature_validation` は、HARP における `candidate_addition` の正式入口である。
この job は `feature_validation` experiment の parent / child run を使って、`start -> append -> finalize` の単位で 1 つの判断テーマを管理する。

`existing_comparison` は `feature_selection` 側の別フローとして扱う。既存 ON 特徴量の整理は `docs/operations/feature_selection_job_usage.md` を参照する。

代表 preset:

- `raw_course_features`
- `turn_direction_feature_set_example`
- `template_feature_set`

preset の正本は `notebook/config/feature_validation_presets/<preset>.yml` である。

## 1. 標準フロー

標準運用は次の 3 段に固定する。

1. `start`
   - baseline と candidate 単独 `single_add` を含む preset を用意する
   - 新規追加特徴量は各 feature ごとに少なくとも 1 本の SHAP-reviewed scenario を持たせる
   - 関連のある新規特徴量を複数まとめて追加する場合は、その関連セットを同時に enable した SHAP-reviewed scenario も用意する
   - `uv run python -m pipeline.jobs.run_feature_validation --preset <preset>` を実行する
2. `append`
   - 単独結果を見て、同じ preset に改善セット `feature_set_add` や必要な `replace_existing` scenario を追加する
   - 同じ parent theme に `--resume-parent-run-id` で追実験を積む
3. `finalize / promotion`
   - parent run の report / runs CSV / MLflow evidence を確認する
   - 追実験が終わったら、人が CLI から `--finalize` を実行して theme を閉じる
   - `採用` の場合だけ人手で `pipeline/config/feature_registry.yml` を更新する

`feature_validation_log.csv` 追記や手動で metrics notebook と SHAP notebook を順番に叩くやり方は標準運用ではない。  
metrics notebook と SHAP notebook は、この job が内部 runner として呼び出す。
metrics notebook は `notebook/tmp/analysis_cache` の Parquet を入力として再利用する前提で運用する。
エージェント運用では、原則として `start` / `append` までを担当し、`finalize` は明示的な CLI 操作でのみ実施する。

## 2. 目的

この job は次をまとめて実行する。

- scenario ごとの feature config 解決
- metrics notebook 実行
- 新規追加特徴量に対する SHAP notebook 実行
- MLflow への parent / child run 記録
- parent report と runs CSV の再生成

依存方向は `pipeline/jobs -> controllers -> usecase` に固定されている。

## 3. 実行コマンド

初回実行:

```bash
uv run python -m pipeline.jobs.run_feature_validation --preset raw_course_features
```

同一 theme への追実験:

```bash
uv run python -m pipeline.jobs.run_feature_validation \
  --preset raw_course_features \
  --resume-parent-run-id <parent_run_id> \
  --only-scenarios add_all_raw,replace_course_condition_history_with_raw \
  --append-note "candidate単独の結果を踏まえて改善セットを追加"
```

theme を閉じる:

```bash
uv run python -m pipeline.jobs.run_feature_validation \
  --preset raw_course_features \
  --resume-parent-run-id <parent_run_id> \
  --finalize \
  --append-note "追加実験を反映して最終判定を確定"
```

ヘルプ:

```bash
uv run python -m pipeline.jobs.run_feature_validation --help
```

## 4. CLI 引数

| 引数 | 必須 | 既定値 | 用途 |
|---|---|---|---|
| `--preset` | 任意 | `raw_course_features` | 検証 preset 名 |
| `--report-out` | 任意 | preset 既定値 | start 時の最終レポート出力先 |
| `--runs-csv-out` | 任意 | preset 既定値 | start 時の scenario 一覧 CSV 出力先 |
| `--run-log-dir` | 任意 | preset 既定値 | start 時の実行ログと中間 artifact の出力先 |
| `--git-commit` | 任意 | `git rev-parse HEAD` | レポートと MLflow に紐付ける commit |
| `--resume-parent-run-id` | 任意 | なし | 既存 theme へ append するときの parent run ID |
| `--only-scenarios` | 任意 | なし | append 時に再実行する scenario 名を comma 区切りで指定 |
| `--finalize` | 任意 | `false` | theme を `finalized` にして以後の append を拒否する |
| `--append-note` | 任意 | なし | append / finalize の理由を report に追記する |

通常は `--preset` だけでよい。  
append 時は `report_out` / `runs_csv_out` / `run_log_dir` は親 theme 側が正本で、CLI override は採用されない。

## 5. 前提条件

- `uv` 環境が利用できること
- dbt 変更を含む検証では、事前に `scripts/refresh_analysis_cache.sh` で Parquet cache を更新しておくこと
  - `scripts/refresh_analysis_cache.sh --full-refresh`
  - dbt をすでに実行済みなら `scripts/refresh_analysis_cache.sh --skip-dbt`
- `pipeline/config/feature_registry.yml` に base feature set 定義があること
- `notebook/config/feature_validation_presets/<preset>.yml` が存在すること
- metrics notebook: `notebook/prd/lgbm_fuku_platt_metrics.py`
- SHAP notebook: `notebook/lab/lgbm_fuku_platt_shap.py`
- local MLflow tracking root が利用可能であること
  - 既定値: Git common root 配下の `mlflow/`（linked worktree でも共通）
- legacy local store `notebook/tmp/mlflow` が残っている場合は、先に migration を 1 回実行すること
  - `uv run python -m pipeline.jobs.migrate_mlflow_store`
- `uv run python -c "import mlflow"` が成功すること

## 6. `start / append / finalize` の使い分け

### 6.1 start

- 新しい parent run を作る
- baseline と candidate 単独 `single_add` をまず流す
- 例:
  - `baseline_existing`
  - `add_candidate_feature`

### 6.2 append

- 既存 parent run に child run を追加する
- 単独結果を見て、改善セット `feature_set_add` や `replace_existing` を追加する
- 関連特徴を複数追加した theme では、必要に応じて related set を同時に有効化した SHAP-reviewed scenario を append する
- `--only-scenarios` 未指定時は preset の全 scenario を再実行する
- append 後の report / runs CSV / summary は parent 全体の effective result から再生成される

### 6.3 finalize

- theme を `finalized` にして結論を閉じる
- finalized theme には以後 append できない
- 運用上は人が CLI から明示的に実行する。エージェントは原則ここを自動実行しない
- 新しい仮説としてやり直す場合だけ、新しい parent run を切る

## 7. `candidate単独 -> 改善セットappend` の設計ガイド

同じ判断テーマの中では、preset 名を維持したまま scenario を拡張する。

推奨構成:

1. `baseline_existing`
2. candidate 単独 `single_add`
3. 改善セット `feature_set_add`
4. 必要時だけ `replace_existing`

代表例:

- 初回 preset
  - `baseline_existing`
  - `add_turn_direction_raw`
- 追実験で追加
  - `add_all_raw`
  - `replace_course_condition_history_with_raw`

改善セット比較を別 theme や `feature_selection` に切り替えず、同じ `feature_validation` theme に append するのが標準である。

## 8. 実行時の挙動

job は次の順で進む。

1. `start` なら parent run を新規作成する
2. target scenario を child run として実行する
3. 各 scenario ごとに一時 feature config を生成する
4. metrics notebook をその config で実行する
   - 入力データは DB を毎回直接読むのではなく、更新済みの Parquet cache を再利用する前提である
5. SHAP 対象 scenario は同じ child run の中で SHAP を実行する
   - 新規追加特徴量は final report に SHAP 所見が残るよう、少なくとも 1 つの SHAP-reviewed scenario を持つ
   - 関連特徴セットを確認した場合は、`comparison_features` を通じてそのセットを記録する
6. parent 全体の effective result を再構築する
7. runs CSV と最終レポートを出力する
8. parent run を `FINISHED` で閉じる

run 構成は次のとおり。

- `1判断テーマ = 1 parent run`
- `1scenario = 1 child run`
- `rerun attempt` は同じ parent run 配下に追加される

source registry `pipeline/config/feature_registry.yml` は validation 実行中に編集しない。  
scenario 差分は `outputs/.../inputs/features_*.yml` に一時生成される。

## 9. 生成物

主な生成物は次の 3 系統に分かれる。

### Git 管理対象

- `notebook/report/features/*_feature_definition_validation_report.md`

### Git ignore 対象の runtime artifact

- `notebook/report/results/*_runs.csv`
- `notebook/report/shap/*.md`
- `mlflow/`
- `notebook/prd/outputs/feature_validation/`
- `notebook/prd/outputs/artifacts/feature_validation/`
- `notebook/prd/outputs/metadata/feature_validation/`
- `outputs/*_logs_*/`
- `outputs/*/inputs/features_*.yml`
- `outputs/*/parent_artifacts/`

### 実行後に標準出力へ出る情報

job 完了後は次が表示される。

```text
decision=...
parent_run_id=...
theme_status=...
theme_revision=...
report=...
runs_csv=...
```

## 10. MLflow での確認

local tracking を使う場合の UI 起動例:

```bash
uv run mlflow ui --backend-store-uri "$(git rev-parse --path-format=absolute --git-common-dir | sed 's#/.git$##')/mlflow" --port 5050
```

確認ポイント:

- parent run が 1 本できていること
- `baseline_existing` と candidate / improved set の child run が並んでいること
- parent run に最終レポートと runs CSV があること
- SHAP 実行 scenario の child run に `shap` artifact があること
- final report に candidate dependence と comparison set、`dependence の形の考察` が残っていること
- append した場合、同一 parent run の `theme_revision` が進んでいること

Git に残す根拠 ID は parent run の `mlflow_run_id` を使う。

## 11. 出力の見方

### 最終レポート

確認する主な章:

- `## 6. 検証結果`
- `## 6.6 追実験メモ`
- `## 7. 最終判定`
- `## 8. 推奨反映内容`
- `## 9. MLflow 紐付け情報`

report の「推奨反映内容」は validation job が source registry を書き換えた意味ではない。  
一時 config を使って検証した結果から、人間が promotion するときの反映方針を示している。

### runs CSV

主な列:

- `scenario`
- `scenario_run_id`
- `enabled_features`
- `enabled_cat_features`
- `features_config_path`
- `auc`
- `logloss`
- `brier`
- `delta_auc`
- `delta_logloss`
- `delta_brier`
- `shap_report`
- `decision`

`runs CSV` は parent 全体の effective scenario を 1 行ずつ表す。  
古い attempt は MLflow 履歴に残るが、CSV では最新 successful だけが出る。

## 12. 採用後の反映

`採用` の場合だけ、validation のあとに人手で feature registry を更新する。

1. `pipeline/config/feature_registry.yml` の対象 feature に `set_status` を反映する
2. 必要なら `uv run python -m pipeline.jobs.export_feature_contract` で feature contract へ反映する
3. 必要なら render utility で対象 feature set の実体を確認する

contract へ反映する場合:

```bash
uv run python -m pipeline.jobs.export_feature_contract \
  --feature-set place_v1 \
  --target contracts/features/place/place_v1.yaml \
  --force
```

確認だけしたい場合:

```bash
uv run python -m pipeline.jobs.render_feature_set \
  --feature-set place_v1 \
  --mode production \
  --stdout
```

registry 反映を省くと、次回の `feature_set` preset が古い registry 定義を土台にして drift する。

## 13. よくある確認ポイント

### source registry を触っていないか

job 終了後に source `pipeline/config/feature_registry.yml` が変更されていないことを確認する。  
検証用の差分は `outputs/.../inputs/features_*.yml` に出る。

### append 時に path が変わっていないか

append 時は親 theme の `report_out` / `runs_csv_out` / `run_log_dir` が優先される。  
別パスを CLI で指定しても、runtime artifact は同じ `outputs/...` 配下に集約される。

### 途中失敗したとき

- 開始済み scenario run は `FAILED`
- start 中の parent run は `FAILED`
- append 中に失敗した場合、parent theme は `open` のまま残る
- failed run は即削除せず、原因確認後に手動削除する

### SHAP path が絶対 path になっていないか

`runs CSV` と最終レポート中の SHAP report path は `notebook/report/shap/...` 形式であることを確認する。

## 14. 制約

- artifact store は local filesystem 前提
- MLflow backend は local file store 前提
- append 対象は `theme_status=open` を持つ parent run に限る

## 15. 新しい preset の追加

新しい検証案件を追加するときは Python の hardcode を増やさず、次を行う。

1. `notebook/config/feature_validation_presets/<preset>.yml` を追加する
2. `validation`, `outputs`, `report`, `target_features`, `scenarios` を定義する
3. 初回は `single_add` 中心で start する
4. 必要なら同じ preset に `feature_set_add` / `replace_existing` scenario を足して append する

固定ルール:

- `scenarios[0]` は `baseline_existing`
- 各候補特徴量について `single_add` scenario を 1 本ずつ入れる
- 候補特徴量をまとめて有効化する `feature_set_add` scenario を 1 本入れる
- 類似既存特徴量との比較用に `replace_existing` scenario を 1 本以上入れる
- `scenario_name` は一意
- `shap.candidate_feature` は `target_features.feature_name` に存在すること
- `single_add` + SHAP の scenario は対象 feature を明示的に含めること

scenario の feature 指定方法は 2 通りある。

- `feature_set`: `base_feature_set_name` を土台に `include_features` / `exclude_features` を差分指定する推奨方式
- `toggles`: 既存 feature config を ON/OFF する互換方式

新規 preset を作るときは、まず  
`notebook/config/feature_validation_presets/template_feature_set.yml`  
を複製して埋めるのが最短である。
