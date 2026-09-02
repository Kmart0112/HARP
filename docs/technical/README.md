# Technical Docs

HARP の技術スタックを、単一の大きな一覧ではなく実行基盤ごとに分けて整理する。

## 入口

- [python_runtime.md](python_runtime.md): Python、uv、パッケージ、実行方法
- [data_platform.md](data_platform.md): PostgreSQL、Docker、dbt、Superset
- [dbt_documentation_guidelines.md](dbt_documentation_guidelines.md): dbt docs / YAML descriptions の書き方
- [ml_experiment_stack.md](ml_experiment_stack.md): LightGBM、scikit-learn、MLflow、SHAP、marimo

## 方針

実装は Hexagonal Architecture の責務分離に従う。外部 I/O は adapter 側へ寄せ、学習・推論・評価の純計算は `src/harp/core` に置く。

詳細な依存方向は [../design/hexagonal_responsibility_split.md](../design/hexagonal_responsibility_split.md) を参照する。
