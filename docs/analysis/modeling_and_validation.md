# モデリングと検証

## 目的

HARP のモデル検証は、単にスコアが上がったかを見るだけではなく、再現可能な比較、確率校正、特徴量採否、解釈妥当性をまとめて残すことを目的にする。

## 予測モデル

現行の中心は LightGBM による二値分類。主なタスクは以下。

- `is_place`: 複勝圏に入るか
- `is_win`: 勝つか
- 券種別・ペア別確率は、必要に応じて別設計として扱う

モデル本体や指標計算の純粋ロジックは `src/harp/core` に寄せる。job や notebook は、データ取得、設定、実行、出力確認の入口として使う。

## 評価指標

標準の比較軸は以下。

- `AUC`: 順位付け性能
- `LogLoss`: 確率の鋭さと外し方
- `Brier`: 確率校正を含む誤差
- セグメント別指標: 条件ごとに効いている/壊れている箇所を見る

馬券判断に進む場合でも、最初から ROI だけで特徴量採否を決めない。まず予測と校正を見て、その後にオッズとの関係を見る。

## 校正

LightGBM の出力確率は、そのまま賭け判断に使う前に校正を確認する。既存 notebook では Platt calibration と log-odds を組み合わせた確認が使われている。

校正は「当たりそうな順に並べる」能力とは別物として扱う。AUC が良くても、確率が過大・過小に出ていれば EV 判断が壊れる。

## 特徴量検証

特徴量検証は preset を起点に、baseline、候補追加、置換、改善セットなどの scenario を比較する。正式な運用では MLflow parent run の下に child run を積み、レポートと CSV を出力する。

主な入口:

- [../operations/feature_validation_job_usage.md](../operations/feature_validation_job_usage.md)
- [../operations/feature_selection_job_usage.md](../operations/feature_selection_job_usage.md)
- [../operations/mlflow_operations_rules.md](../operations/mlflow_operations_rules.md)

判断は `採用 / 保留 / 不採用` のように明示し、理由と根拠 run を残す。

## SHAP レビュー

SHAP は主判定指標ではなく、特徴量の使われ方、リーク疑い、既存特徴量との重複、依存形の妥当性を見るための補助線として使う。

metrics が改善していても、SHAP で明らかなリークや不自然な依存が見える場合は保留にする。metrics が未改善の場合も、なぜ効かなかったかを知見として回収できる。
