# Notebook 運用ガイド

## 目的
- notebook の配置ルールと記述ルールを統一し、再現性と保守性を上げる。

## 使い方
- notebook の標準は `marimo` とする。
- 新規 notebook は原則 `notebook/lab` に作成する。
- 正式指標として繰り返し利用する notebook は `notebook/prd` に配置する。

## 内容ルール
- notebook 内のロジックは最小化し、可能な限り `src/harp/core` に隠蔽する。
- DB、ファイル、trackingなどの外部I/Oは既存のPort / Adapter / Controllerを再利用し、notebook専用のambient settings経路を作らない。
- 各セルには「何を実行するセルか」の概要を必ず記載する。
- 数値やグラフを提示する場合は、その読み方・見るべきポイント・解釈上の注意を説明する Markdown セルを必ず入れる。

## marimo の interactive / script mode 運用
- `uv run marimo run <notebook.py>` はブラウザUI付きで実行する。
- `uv run python <notebook.py>` または `uv run <notebook.py>` は非対話の script mode として notebook を一度だけ実行する。
- UI付き notebook を script mode で実行してもユーザー操作は発生しないため、widget 値は原則として初期値で扱われる前提で設計する。
- button 押下待ちや form 送信待ちのような対話前提フローは、script mode では自動実行に切り替える。
- mode 判定が必要な場合は `mo.app_meta().mode == "script"` を使う。

## marimo の設定値入力ルール
- 再現実行、バッチ実行、定期実行を想定する notebook は、CLI引数から設定値を受け取れるようにする。
- UI と CLI の二重管理は避け、最終的には同じ設定オブジェクトに正規化して下流へ渡す。
- CLI引数未指定時の既定値は、可能な限り UI の初期値と揃える。
- exploratory な一時 notebook を除き、script mode で条件変更が必要になりうる値は UI 初期値だけに閉じ込めない。

## HARP runtime config の標準入口

- repo内のnotebookは、入口セルで`pipeline.runtime_settings.load_pipeline_runtime_config()`を一度だけ呼ぶ。
- DB URL、training / prediction mart、MLflow URI、feature registry pathは、返された`HarpRuntimeConfig`から受け取る。
- `src/harp`側で環境変数、`.env`、削除済みの`get_settings()`を読まない。
- feature registry / contract YAMLは`NotebookFeatureConfigController(config)`経由で解決する。notebook内でregistry schemaを再実装しない。
- notebook固有のCLI / UI値は、runtime configを上書きする明示値として扱い、最終的に一つの設定オブジェクトへ正規化する。

### 標準パターン

```python
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from harp.controllers import NotebookFeatureConfigController
from pipeline.runtime_settings import load_pipeline_runtime_config

runtime_config = load_pipeline_runtime_config()
notebook_config_controller = NotebookFeatureConfigController(runtime_config)
```

繰り返し利用する計算は`src/harp/core`、業務手順はUseCase、外部I/OはAdapterへ移す。notebookは探索、表示、実行パラメータの入口に限定する。

### 推奨パターン
```python
@app.cell
def _(mo):
    is_script_mode = mo.app_meta().mode == "script"
    return (is_script_mode,)


@app.cell
def _(is_script_mode, ui_config):
    if is_script_mode:
        config = load_config_from_args()
    else:
        config = load_config_from_ui(ui_config)
    return (config,)
```

## 特徴量検証 notebook の位置づけ
- 新規特徴量の正式検証入口は notebook 直叩きではなく `uv run python -m pipeline.jobs.run_feature_validation` とする。
- metrics notebook `notebook/prd/lgbm_fuku_platt_metrics.py` と SHAP notebook `notebook/lab/lgbm_fuku_platt_shap.py` は、`feature_validation` job の内部 runner として使うのが標準である。
- `candidate_addition` の正式フローは `baseline -> single_add -> feature_set_add append -> finalize/promotion` とする。
- ただし当面は、エージェントは `finalize` を実行せず、theme の終了は人が CLI から実施する。
- 新規追加特徴量は SHAP を必須とし、最終レポートにも SHAP 所見を残す。
- 関連のある新規特徴量を複数まとめて追加する場合は、その関連セットで dependence を確認できる SHAP scenario を用意する。
- `feature_selection` の正式入口は `uv run python -m pipeline.jobs.run_feature_selection` とし、candidate 導線の続きとしては扱わない。
- `feature_validation_log.csv` への append は標準運用に含めない。

参照:

- `docs/operations/feature_validation_job_usage.md`
- `docs/operations/feature_selection_job_usage.md`

## scripts ディレクトリ運用
- `notebook/scripts` には一時的なスクリプトを置いてよい。
- ここはコーディングエージェントが検証時に自由に利用する作業領域とする。

## 重い検証時の事故予防チェック（LGBM/feature validation）
- 自動検証スクリプトでは `marimo run ...` ではなく `uv run python notebook/prd/lgbm_fuku_platt_metrics.py` を使う。
  - `marimo run` はサーバー待機で終了しないケースがあり、バッチ実行がハングする。
- 実行前に空き容量を確認し、目安 2GiB 以上を確保する。
  - `df -h .`
  - 不足時は `uv cache clean --force` を優先して実行する。
- `feature-validation` と metrics notebook は `notebook/tmp/analysis_cache` の Parquet を再利用する前提で運用する。
- DB定義変更後は、検証の前に `scripts/refresh_analysis_cache.sh` で Parquet を更新する。
  - 例: `scripts/refresh_analysis_cache.sh --full-refresh`
  - dbt 実行済みなら `scripts/refresh_analysis_cache.sh --skip-dbt`
  - parquet 読込失敗時も同じ shell で再出力する。
- 容量不足で評価本体まで落としたくない場合は `HARP_SKIP_ANALYSIS_CACHE_WRITE=1` を付けて cache 保存だけ止める。
  - 例: `HARP_SKIP_ANALYSIS_CACHE_WRITE=1 uv run python notebook/prd/lgbm_fuku_platt_metrics.py`
- `notebook/tmp/analysis_cache/.gitignore` は維持する。
- source registry `pipeline/config/feature_registry.yml` は validation 実行中に編集しない。

### 実行前テンプレート（例）
```bash
df -h .
uv cache clean --force
set -a; source .env; set +a
scripts/refresh_analysis_cache.sh --full-refresh
uv run python notebook/scripts/<validation_script>.py
```
