# HARP MLflow 同一テーマ追実験 Append 詳細設計

最終更新: 2026-03-16

## 0. 目的

- 既存の `feature_validation` / `feature_selection` フローに対して、同一の判断テーマへ追実験を積み増せるようにする。
- 追実験の正式な証跡は MLflow の同一 parent run 配下に集約する。
- Hexagonal の責務分離を維持し、追実験の追加は `pipeline/jobs -> controllers -> usecase -> interface/ports -> adapters/driven` の依存方向で実装する。
- まずは `feature_validation` を先行対応し、`feature_selection` は副作用整理後に横展開する。

## 1. 背景

現状の特徴量検証 job は「1回の job 実行 = 1 parent run = 1回で閉じる最終レポート」を前提としている。

- `feature_validation` は毎回 parent run を新規作成し、scenario child run を流したあと report / runs CSV / summary を書いて parent run を `FINISHED` にする。
- `feature_selection` も同様に parent run を新規作成して閉じる。
- job / usecase は「今回の invocation で実行した scenario 結果」だけを手元の `scenario_results` として保持し、そこから report を作る。

この構造では次ができない。

- 既存 parent run に新しい scenario child run を追加する
- 同じ scenario を再実行し、旧 run を履歴として残しつつ report 上は最新結果に差し替える
- 追実験後に parent 全体の report / summary を再生成する

## 2. 設計方針

### 2.1 追実験の単位

- `1 parent run = 1 judgment theme` を維持する
- `1 child run = 1 scenario attempt` と定義し直す
- 同じ `scenario_name` を複数回実行してよい
- report / summary 上で採用するのは「各 scenario の最新 successful attempt」とする

### 2.2 ライフサイクル

同一テーマの運用を次の 3 モードに分ける。

1. `start`
   - 新しい parent run を作る
   - scenario を実行する
   - report / runs CSV / summary を生成する
   - parent run は `OPEN` 状態のまま残す
2. `append`
   - 既存 parent run を指定して child run を追加する
   - 既存 child run 群と今回の結果を束ね、report / runs CSV / summary を再生成する
   - parent run は引き続き `OPEN`
3. `finalize`
   - parent 単位の最終 decision を確定する
   - promotion 対象の出力を確定する
   - parent run を `FINISHED` にする

補足:

- `FAILED` は現在と同じく異常終了時に付与する
- `OPEN` / `FINALIZED` は MLflow status ではなく tag で管理する

### 2.3 source of truth

追実験時の再集計は、ローカルの一時 CSV ではなく MLflow 上の child run 情報を正本とする。

- child run の params / metrics / tags
- child run artifact の `summary.json`
- parent run tags / params / artifact

ローカルファイルは cache ではあっても正本にしない。

## 3. 状態モデル

### 3.1 parent run tags

parent run には少なくとも次の tag を持たせる。

- `run_role=parent`
- `theme_status=open|finalized|failed`
- `theme_kind=feature_validation|feature_selection`
- `theme_name=<validation_name>`
- `preset_name=<preset_name>`
- `report_path=<repo-relative or absolute path>`
- `runs_csv_path=<repo-relative or absolute path>`
- `theme_revision=<int>`
- `git_commit=<commit>`

`feature_selection` では追加で次を持つ。

- `decisions_csv_path`
- `selected_feature_set_snapshot_path`
- `feature_registry_path`

### 3.2 child run tags

child run には少なくとも次の tag を持たせる。

- `run_role=scenario`
- `scenario_name=<logical name>`
- `scenario_attempt=<1..n>`
- `attempt_status=successful|failed|superseded`
- `parent_theme_status_at_run=open`
- `validation_mode=<mode>`

必要なら次も持つ。

- `supersedes_run_id=<old_run_id>`
- `candidate_feature=<name>`
- `comparison_features=<pipe-joined names>`

### 3.3 parent summary の決め方

parent summary は child run 群から再構築する。

- child run を `scenario_name` ごとに束ねる
- `FAILED` を除いた successful attempt を時系列で並べる
- 最新 successful attempt を `effective result` とする
- effective result 群から report / runs CSV / decision を生成する

## 4. CLI / job 仕様

### 4.1 `run_feature_validation.py`

次の引数を追加する。

- `--resume-parent-run-id`
- `--only-scenarios`
- `--finalize`
- `--append-note`

意味:

- `--resume-parent-run-id` なし: `start`
- `--resume-parent-run-id` あり + `--finalize` なし: `append`
- `--resume-parent-run-id` あり + `--finalize` あり: `append + finalize`

`--only-scenarios` は comma 区切りで受け、preset の scenario 全体ではなく一部だけを再実行する。

### 4.2 `run_feature_selection.py`

同様の引数を追加する。`feature_selection` では per-set artifact を source of truth にせず、finalize 後の feature registry 更新だけを正式反映とする。

## 5. DTO 変更

### 5.1 `FeatureValidationCommand`

追加:

- `resume_parent_run_id: str | None`
- `only_scenarios: tuple[str, ...]`
- `finalize: bool`
- `append_note: str | None`
- `preset_name: str`

### 5.2 `FeatureValidationRequest`

追加:

- `resume_parent_run_id: str | None`
- `scenario_filter: tuple[str, ...]`
- `finalize: bool`
- `append_note: str | None`
- `preset_name: str`

### 5.3 `FeatureValidationResult`

追加:

- `theme_status: str`
- `theme_revision: int`
- `effective_scenario_run_ids: dict[str, str]`
- `new_scenario_run_ids: dict[str, str]`

### 5.4 `FeatureSelection*`

`feature_selection` にも同様の項目を入れる。  
ただし registry 反映は finalize 後の運用に寄せるため、`FeatureSelectionResult` には次を追加する。

- `registry_updated: bool`

## 6. TrackingPort 拡張

現状の `TrackingPort` は write API のみで read API がない。  
append では parent 配下の child run を再読込して report を再構築する必要があるため、read API を追加する。

### 6.1 追加する Port

- `get_run(run_id: str) -> TrackingRunRecord`
- `list_child_runs(parent_run_id: str) -> tuple[TrackingRunRecord, ...]`
- `read_dict_artifact(run_id: str, artifact_file: str) -> dict[str, object]`

### 6.2 `TrackingRunRecord`

最低限の項目:

- `run_id`
- `run_name`
- `status`
- `start_time`
- `end_time`
- `params`
- `metrics`
- `tags`

補足:

- append の report 再構築で必要な scenario 情報は child artifact の `summary.json` に寄せる
- tracker 側で artifact directory 全体を読む必要はない

## 7. `feature_validation` UseCase 詳細

### 7.1 start

1. request を検証する
2. parent run を新規作成する
3. parent run に `theme_status=open`, `theme_revision=1` を付ける
4. scenario を実行する
5. child run ごとに `summary.json` を記録する
6. parent 配下の effective result を集計する
7. report / runs CSV / parent summary を生成する
8. parent artifact を更新する
9. parent は close せず、tag 上は `open`

### 7.2 append

1. `resume_parent_run_id` を受ける
2. parent run を読み、`theme_status=open` を確認する
3. 既存 child run を読み、`scenario_name -> latest successful attempt` を構築する
4. `scenario_filter` がある場合は対象 scenario だけ今回実行する
5. 新しい child run を parent 配下に追加する
6. 旧 effective run と同名なら、新しい child run を effective に置き換える
7. parent 全体の effective result から report / runs CSV / parent summary を再生成する
8. parent の `theme_revision` をインクリメントする

### 7.3 finalize

1. parent の effective result を再計算する
2. 最終 decision を確定する
3. parent tag を `theme_status=finalized` にする
4. parent run を `FINISHED` にする

### 7.4 child `summary.json`

child artifact の `summary.json` は append 再構築に必要な情報をすべて含むようにする。

必要項目:

- `scenario_name`
- `scenario_attempt`
- `validation_mode`
- `enabled_features`
- `enabled_cat_features`
- `features_config_path`
- `auc`
- `logloss`
- `brier`
- `delta_auc`
- `delta_logloss`
- `delta_brier`
- `metrics_judgement`
- `decision`
- `shap_report_path`
- `candidate_feature`
- `comparison_features`

## 8. `feature_selection` UseCase 詳細

`feature_selection` は append 中に source of truth を更新しない。  
append を入れる前に、正式反映は finalize 後の feature registry 更新へ寄せる。

### 8.1 start / append 中に禁止すること

- `feature_registry_path` の更新
- selected feature set の「正式反映」

### 8.2 start / append 中に許可すること

- 一時的な `selected_feature_set_snapshot_out` の生成
- decisions CSV の再生成
- report の再生成
- parent summary の再生成

### 8.3 finalize でだけ行うこと

- final winner set の確定
- `feature_registry_path` への反映
- `registry_updated=true` の返却

## 9. report / CSV 再生成ルール

### 9.1 `runs_csv`

- 1行 = 1 effective scenario
- 旧 attempt は履歴として MLflow に残すが CSV には出さない
- 必要なら `scenario_attempt` 列を追加して「現在採用中の attempt 番号」を書く

### 9.2 report

- report は毎回 parent 全体を再生成する
- 旧本文への部分 patch はしない
- `theme_revision` を本文に出す
- `追実験メモ` セクションを追加し、append 時の `append_note` を記録する

### 9.3 decisions CSV

- `feature_selection` だけで出す
- parent 全体の effective result から都度作り直す

## 10. エラー処理

### 10.1 append 失敗

- 途中まで開始した child run は `FAILED`
- parent は `theme_status=open` を維持する
- 直前 revision の report / summary は正として残す

### 10.2 finalize 失敗

- final decision を parent tag に書く前に失敗した場合、parent は `open`
- `finalize` 再実行を許可する

### 10.3 finalized parent への append

- 原則禁止
- `theme_status=finalized` の parent へ `append` はできない
- 追加検証が必要になったら新しい parent run を切る

## 11. 変更対象ファイル

### 11.1 `feature_validation` 先行実装

- `pipeline/jobs/run_feature_validation.py`
- `src/harp/controllers/feature_validation.py`
- `src/harp/usecase/feature_validation/dto.py`
- `src/harp/usecase/feature_validation/usecase.py`
- `src/harp/interface/ports/tracking_ports.py`
- `src/harp/adapters/driven/tracking/mlflow_tracking_adapter.py`
- `tests/flows/test_feature_validation_flow.py`
- `tests/integrations/test_storage_and_tracking.py`

### 11.2 `feature_selection` 横展開

- `pipeline/jobs/run_feature_selection.py`
- `src/harp/controllers/feature_selection.py`
- `src/harp/usecase/feature_selection/dto.py`
- `src/harp/usecase/feature_selection/usecase.py`
- `tests/flows/test_feature_selection_flow.py`

## 12. テスト方針

### 12.1 UseCase

- start で parent が `open` になる
- append で既存 child run を再読込できる
- 同名 scenario の再実行で latest successful が effective になる
- append 失敗時に parent が `open` のまま保たれる
- finalize で parent が `finalized` になる

### 12.2 Adapter

- MLflow adapter が parent 配下 child run を列挙できる
- `summary.json` を読める
- parent / child tag の更新ができる

### 12.3 Job

- `--resume-parent-run-id`
- `--only-scenarios`
- `--finalize`

## 13. 段階導入

### Phase A

- `feature_validation` に `start / append / finalize` を導入
- report / runs CSV の全再生成を parent 単位に変更

### Phase B

- `feature_selection` の source of truth 更新を finalize 後の registry 反映へ寄せる
- `feature_selection` に append を導入

### Phase C

- append history の UI 表示や運用ガイドを整備する
- 必要なら `theme_id` ベース検索や parent reopen helper を追加する

## 14. 未決事項

- parent run を MLflow status 上でずっと `RUNNING` に保つか、status は `FINISHED` にして tag 上だけ `open` にするか
- append ごとの report revision を artifact path に世代保持するか、常に最新で上書きするか
- `only_scenarios` 未指定の append を「preset 全 scenario 再実行」にするか「0件エラー」にするか
- `feature_selection` の interim decision を report にどこまで書くか

## 15. 採用判断

本設計では次を採用する。

- 追実験の正本は同一 parent run 配下に集約する
- child run は `scenario attempt` として扱う
- report / CSV / summary は parent 全体から毎回再生成する
- `feature_validation` を先に対応する
- `feature_selection` は registry 反映を finalize 後に分離してから対応する
