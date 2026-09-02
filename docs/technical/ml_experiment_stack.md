# ML と実験管理スタック

## LightGBM / scikit-learn

現行の主力モデルは LightGBM の二値分類。scikit-learn は指標計算、校正、補助モデルに使う。

代表的な評価指標:

- `roc_auc_score`
- `log_loss`
- `brier_score_loss`

## MLflow

MLflow は正式な実験証跡の保存先。feature validation / feature selection では parent run と child run を使い、scenario ごとの metrics と artifact を管理する。

運用ルールは [../operations/mlflow_operations_rules.md](../operations/mlflow_operations_rules.md) を参照する。

## SHAP

SHAP は特徴量の採否判断を補助するために使う。主判定は metrics とし、SHAP は依存形、重複、リーク疑い、不自然な寄与を確認する。

## marimo

notebook の標準は marimo。新規検証は `notebook/lab`、正式指標として繰り返し使うものは `notebook/prd` に置く。

script mode での再現実行を前提にする notebook は、UI 初期値だけに依存せず CLI 引数から設定値を受け取れるようにする。

notebook 運用は [../operations/notebook_usage.md](../operations/notebook_usage.md) を参照する。

## 補助スタック

- `matplotlib`: 評価グラフや簡易可視化
- `pymc`: 階層モデルや不確実性評価の候補
- `streamlit`: 必要に応じた簡易 UI
- `cognee`: 知識検索やメモ運用の補助
