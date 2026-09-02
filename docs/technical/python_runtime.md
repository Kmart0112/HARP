# Python 実行基盤

## Runtime

- Python: `>=3.11`
- パッケージ定義: `pyproject.toml`
- 解決済みバージョン: `uv.lock`
- 実行: 原則 `uv`
- package root: `src/harp`

依存定義の正本は `pyproject.toml`、再現用 lockfile は `uv.lock` とする。
`requirements.txt` や別形式の lockfile は並行管理しない。

初回セットアップ:

```bash
uv sync
```

Python スクリプトの実行・検証は、原則として `uv` 環境を使う。
`pipeline/jobs` の job は direct script path ではなく、repo root から module として起動する。

```bash
uv run python -m pipeline.jobs.run_feature_validation --preset raw_course_features
```

## 主な依存

- `pandas`, `numpy`: 表データ処理
- `SQLAlchemy`, `psycopg`: PostgreSQL 接続
- `lightgbm`, `scikit-learn`: 学習、校正、指標計算
- `mlflow`: 実験管理
- `marimo`: notebook
- `shap`: モデル解釈
- `pytest`: テスト

`cognee` は本体の学習・推論には不要なため、`knowledge` extra に分離する。
Cognee のラッパースクリプトは必要な extra を自動で有効にする。手動で環境を同期する場合は次を使う。

```bash
uv sync --extra knowledge
```

## 実装配置

- `src/harp/core`: I/O を持たない純粋な学習・推論・評価ロジック
- `src/harp/usecase`: 手順オーケストレーション
- `src/harp/interface/ports`: 外部 I/O 境界の Protocol
- `src/harp/adapters`: CLI、DB、ファイル、MLflow などの adapter
- `pipeline/jobs`: 実行コマンドの入口

配置判断で迷った場合は [../design/hexagonal_responsibility_split.md](../design/hexagonal_responsibility_split.md) を優先する。
