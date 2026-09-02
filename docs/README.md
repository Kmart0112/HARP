# HARP Docs Index

このファイルは、`docs/` 以下の入口です。README は概要だけに寄せ、具体的な分析方法、技術スタック、運用手順、設計判断はここから辿ります。

`docs/` は採用済みの正本に寄せ、実装前の設計メモ、調査途中の案、TODO は公開対象外の作業メモとして管理します。

## まず見るもの

- [analysis/README.md](analysis/README.md): 分析方法の全体像
- [technical/README.md](technical/README.md): 技術スタックと実行基盤
- [operations/local_environment.md](operations/local_environment.md): ローカル環境と PostgreSQL/Docker
- [design/hexagonal_responsibility_split.md](design/hexagonal_responsibility_split.md): 実装責務分離の正本
- [knowledge/README.md](knowledge/README.md): 実験や調査から分かったことの知見置き場

## カテゴリ

### 分析方法

- [analysis/data_preparation.md](analysis/data_preparation.md): dbt、mart、特徴量データ作成
- [analysis/modeling_and_validation.md](analysis/modeling_and_validation.md): LightGBM、校正、特徴量検証、SHAP
- [analysis/betting_decisions.md](analysis/betting_decisions.md): 確率から馬券判断へつなぐ考え方

### 技術スタック

- [technical/python_runtime.md](technical/python_runtime.md): Python、uv、実行コマンドの基本
- [technical/data_platform.md](technical/data_platform.md): PostgreSQL、Docker、dbt、Superset
- [technical/dbt_documentation_guidelines.md](technical/dbt_documentation_guidelines.md): dbt docs / YAML descriptions の書き方
- [technical/ml_experiment_stack.md](technical/ml_experiment_stack.md): ML/実験管理/notebook 周り

### 設計

- [design/README.md](design/README.md): 設計ドキュメント索引
- [design/hexagonal_responsibility_split.md](design/hexagonal_responsibility_split.md): Hexagonal 責務分離
- [design/harp_strategy_factory_design.md](design/harp_strategy_factory_design.md): 関数優先アーキテクチャの設計補足
- [design/mlflow_feature_validation_usecase_design.md](design/mlflow_feature_validation_usecase_design.md): 特徴量検証 usecase 設計
- [design/mlflow_theme_append_design.md](design/mlflow_theme_append_design.md): MLflow 追実験 append/finalize 設計

### 運用

- [operations/local_environment.md](operations/local_environment.md): ローカル環境構築
- [operations/notebook_usage.md](operations/notebook_usage.md): notebook 運用
- [operations/mlflow_operations_rules.md](operations/mlflow_operations_rules.md): MLflow 運用ルール
- [operations/feature_validation_job_usage.md](operations/feature_validation_job_usage.md): feature validation job
- [operations/feature_selection_job_usage.md](operations/feature_selection_job_usage.md): feature selection job
- [operations/cognee_cli_usage.md](operations/cognee_cli_usage.md): Cognee CLI

### 研究・知見

- [knowledge/](knowledge/): 今まで分かったことの文章ベースのまとめ

PoC、未採用案、実装前 issue、TODO は公開対象外の作業メモで管理する。

## 実装ディレクトリ対応

- `src/harp/core`: 純計算（学習・推論・EV）
- `src/harp/usecase`: ユースケース実行手順
- `src/harp/interface/ports`: Driven Adapter 用 Port
- `src/harp/controllers`: CLI/API 入力の変換と依存注入
- `src/harp/adapters/driven`: DB/ファイル/artifact/manifest I/O 実装
- `pipeline/jobs`: バッチ実行入口
- `dbt/harp`: dbt プロジェクト
- `notebook`: marimo notebook、検証プリセット、評価レポート
