# HARP

Horse Analytics & Risk Prediction.

HARP は、競馬データを分析・特徴量化し、予測モデルと馬券判断の改善につなげるためのプロジェクトです。dbt で分析用データマートを整備し、Python/LightGBM で学習・検証し、MLflow とレポートで判断履歴を残します。

## 目的

- レース、出走馬、調教、オッズなどのデータを学習・推論に使える形へ整える
- 勝率・複勝率などの確率モデルを作り、校正と検証を行う
- 特徴量の採用・保留・不採用を再現可能な証跡として残す
- 確率、オッズ、リスクを分けて見て、買う/買わないの判断に接続する
- 実験で分かったことを `docs/knowledge` に文章として蓄積する

## 全体像

```text
HARP/
  dbt/harp/          # PostgreSQL 上の分析用モデル、特徴量、mart
  src/harp/          # hexagonal 構成のアプリケーションコード
  pipeline/jobs/     # バッチ実行入口
  notebook/          # marimo notebook、検証プリセット、評価レポート
  pipeline/config/   # feature registry などの運用設定
  docs/              # 設計、分析方法、技術スタック、運用、知見
  notes/             # 実装前メモ、調査途中の案、TODO
```

基本の流れは、`dbt` で学習用 mart を作り、`pipeline/jobs` または `notebook/prd` から検証を実行し、MLflow・CSV・Markdown レポートに結果を残す形です。実装上の責務境界は Hexagonal Architecture に寄せています。

## データと生成物

このリポジトリは、JRA-VAN DataLab など利用者が適切な権限を持つデータソースを、ローカルの PostgreSQL に取り込んで利用することを前提としています。生データ、実レースの予測結果、学習済みモデル、MLflow artifact はリポジトリに含めません。

DB 接続情報や API key はコミットせず、`.env.example` を `.env` にコピーしてローカルで設定してください。`outputs/`、`pipeline/artifacts/`、`pipeline/outputs/`、`models/` などの生成物もローカル管理とします。

## Docs 目次

- [docs/README.md](docs/README.md): docs 全体の索引
- [docs/analysis/README.md](docs/analysis/README.md): 分析方法の全体像
- [docs/technical/README.md](docs/technical/README.md): 技術スタックと実行基盤
- [docs/operations/local_environment.md](docs/operations/local_environment.md): ローカル環境と PostgreSQL/Docker
- [docs/operations/notebook_usage.md](docs/operations/notebook_usage.md): notebook 運用
- [docs/operations/mlflow_operations_rules.md](docs/operations/mlflow_operations_rules.md): MLflow 運用ルール
- [docs/design/hexagonal_responsibility_split.md](docs/design/hexagonal_responsibility_split.md): Hexagonal 責務分離の正本
- [docs/design/harp_strategy_factory_design.md](docs/design/harp_strategy_factory_design.md): Strategy/Factory 観点の設計補足
- [docs/knowledge/README.md](docs/knowledge/README.md): 今まで分かったことの文章ベースの知見置き場
- [AGENTS.md](AGENTS.md): エージェント実装時の運用要約

## 主な実行入口

- dbt: [dbt/harp/README.md](dbt/harp/README.md)
- 特徴量検証: [docs/operations/feature_validation_job_usage.md](docs/operations/feature_validation_job_usage.md)
- 特徴量選定: [docs/operations/feature_selection_job_usage.md](docs/operations/feature_selection_job_usage.md)
- notebook: `notebook/lab`, `notebook/prd`, `notebook/report`

## ライセンス

HARP 本体のソースコードとドキュメントは [MIT License](LICENSE) で公開します。
依存ライブラリ、コンテナイメージ、外部サービス、入力データには、それぞれの提供元のライセンスと利用条件が適用されます。
JRA-VAN DataLab などのデータ、学習済みモデル、予測結果、実験 artifact は MIT License の対象に含みません。

README はプロジェクト概要と導線に絞ります。具体的な手順、設計判断、分析方法、技術スタックは `docs/` 以下を参照してください。
