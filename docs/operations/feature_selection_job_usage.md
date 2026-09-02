# Feature Selection Job 使い方

`pipeline.jobs.run_feature_selection` は、HARP における `existing_comparison` の正式入口である。
この job は `feature_selection` experiment の parent / child run を使って、既存 ON 特徴量の keep / drop を `start -> append -> finalize` で管理する。

このフローは `candidate_addition` の続きではない。  
新規特徴量の候補単独検証や改善セット比較は `docs/operations/feature_validation_job_usage.md` の `feature_validation` theme で行う。

## 1. 標準フロー

1. `start`
   - baseline / aggregate / variant scenario を含む preset を用意する
   - `uv run python -m pipeline.jobs.run_feature_selection --preset <preset>` を実行する
2. `append`
   - 追加比較が必要な scenario だけ同じ parent theme に追実験する
3. `finalize`
   - unresolved decision がないことを確認し、`--finalize` で selected feature set を確定する

## 2. 実行コマンド

初回実行:

```bash
uv run python -m pipeline.jobs.run_feature_selection --preset feature_selection_example
```

一部 scenario の追実験:

```bash
uv run python -m pipeline.jobs.run_feature_selection \
  --preset feature_selection_example \
  --resume-parent-run-id <parent_run_id> \
  --only-scenarios variant__variant_family__variant_new \
  --append-note "winner候補を再確認"
```

selected feature set を確定して閉じる:

```bash
uv run python -m pipeline.jobs.run_feature_selection \
  --preset feature_selection_example \
  --resume-parent-run-id <parent_run_id> \
  --finalize \
  --append-note "最終 winner を確定"
```

## 3. CLI 引数

| 引数 | 必須 | 既定値 | 用途 |
|---|---|---|---|
| `--preset` | 必須 | なし | selection preset 名 |
| `--report-out` | 任意 | preset 既定値 | start 時の最終レポート出力先 |
| `--runs-csv-out` | 任意 | preset 既定値 | start 時の scenario 一覧 CSV 出力先 |
| `--decisions-csv-out` | 任意 | preset 既定値 | decision CSV 出力先 |
| `--selected-feature-set-snapshot-out` | 任意 | preset 既定値 | interim selected feature set の snapshot 出力先 |
| `--run-log-dir` | 任意 | preset 既定値 | start 時の実行ログと中間 artifact の出力先 |
| `--git-commit` | 任意 | `git rev-parse HEAD` | レポートと MLflow に紐付ける commit |
| `--resume-parent-run-id` | 任意 | なし | 既存 theme へ append するときの parent run ID |
| `--only-scenarios` | 任意 | なし | append 時に再実行する scenario 名を comma 区切りで指定 |
| `--finalize` | 任意 | `false` | theme を `finalized` にする |
| `--append-note` | 任意 | なし | append / finalize の理由を report に追記する |
append 時は親 theme の `report_out` / `runs_csv_out` / `decisions_csv_out` / `selected_feature_set_snapshot_out` / `run_log_dir` が優先される。

## 4. 運用ルール

- `feature_selection` は既存 ON 特徴量の整理専用で使う
- 新規 candidate の改善セット比較をここへ持ち込まない
- append は `theme_status=open` の parent run に対してだけ許可される
- finalize 時に unresolved decision が残っていたら失敗する
- feature registry への正式反映は finalize 後に行う

## 5. 確認ポイント

- parent run に report / runs CSV / decisions CSV / selected feature set snapshot があること
- append 後に `theme_revision` が進んでいること
- finalized theme に対して append が拒否されること
- finalize 後の反映対象が `pipeline/config/feature_registry.yml` と一致していること
