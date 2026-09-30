# Calibration curveの共通出力

学習済みモデルと正解ラベル付きDatasetから、DB接続・再学習・前処理や校正器の再fitなしで評価する。
単勝/複勝を二値確率として扱い、出走馬1頭を1観測として集計する。

## CLI

HARPリポジトリ直下で実行する。出力先は新しいディレクトリを指定する。

```bash
uv run --no-sync python -m pipeline.jobs.export_calibration \
  --backend lightgbm --model /absolute/path/model.pkl \
  --dataset /absolute/path/evaluation.parquet \
  --split all --output-dir /absolute/path/reports/calibration

uv run --no-sync python -m pipeline.jobs.export_calibration \
  --backend nn --model '<run_id>' --dataset '<prepared_dataset_id>' \
  --split test --device cpu --output-dir /absolute/path/reports/nn-calibration
```

NNは`nn` extraが必要。`--input-root` / `--prepared-root` / `--model-root`は既存NNジョブと同じ保存ルート。
`--checkpoint-id`を省略するとrunの最新checkpointに含まれるbest weightsを使い、実際に使用したIDを記録する。

## Python

```python
from harp.controllers.calibration import export_calibration_report

result = export_calibration_report(
    model=model,
    dataset=dataset,
    split="test",
    output_dir="outputs/calibration/example",
)
print(result.files)
print(result.report.metrics)
```

- LightGBMの`model`はHARP artifact payload（`model`, `feature_names`, `cat_features`, `model_type`等）。
  `dataset`は`BinaryDataset`または教師列付きDataFrame。
- NNの`model`は学習時前処理付き`NnPredictor`、`dataset`は`PreparedNnDataset`。
- ファイル/IDから読みたい場合も同じAPIへ`backend="lightgbm"`または`backend="nn"`を指定する。
- 保存不要なら純粋計算の`harp.core.calibration_prediction.evaluate_calibration(model, dataset, ...)`を使う。
  既存予測表からは`harp.core.calibration.calculate_calibration(samples, ...)`を使う。
  `samples`の必須列は`y_true`, `probability`。任意の`race_id`, `kettonum`の組は一意であること。

## Datasetとsplitの契約

- 既定は`test`。`train` / `validation`も明示指定できる。
- `BinaryDataset`とNN prepared Datasetは保存済みの分割を使う。
- DataFrame/Parquetは`split`列（`train`, `validation`, `test`）を優先し、なければモデルの
  `split_info`と`held_year`または`held_date`から既存の年分割を再現する。
- 評価対象だけを収めたParquet/DataFrameは`--split all`を指定する。
  splitを推測できない入力を黙って全件評価しない。
- 教師列は`model_type`が`place`/`place_platt`なら`is_place`、`win`なら`is_win`。
  別名の教師列には`--target`を指定する。NNは保存されたtaskに応じて`is_place`または`is_win`を使う。
- 別のNN Datasetを渡す場合も、学習モデルと同じ前処理状態・履歴長・taskが必要。
  勝率は単独勝者かつ教師完備のレースを対象とする。校正レポートのLog loss/Brierは馬単位の二値指標で、学習時のレース単位Log lossとは異なる。
  独立にfitされた前処理のDatasetは拒否する。
- NNは全頭の入力を保持したまま推論し、paddingを集計しない。
  prepared Datasetの不完全教師レースは既存の除外規則を引き継ぎ、件数を記録する。
- 不明教師は負例にせず除外数を記録する。不正な確率、二値でない教師、空評価、重複IDは失敗する。
- Parquetにはモデルが必要とする特徴列を学習時と同じ意味・時点で用意する。
  この入口はDB由来の特徴やオッズを再構築しない。単独のParquetから時点の正しさまでは証明できない。

## 確率と出力

既定は補正前の`raw`。LightGBMでは`--probability platt`により保存済みPlatt係数を適用できる。
artifactの`calibration.params.odds_col`で指定される単勝オッズ列が必要。欠損や1未満のオッズを補完しない。
NNへのPlatt指定は未対応として拒否する。

- `calibration.png`: 完全校正線、calibration curve、binごとの件数、確率分布、Brier/Logloss。
- `bins.csv`: bin境界、件数、平均予測確率、実際の的中率。
- `metrics.json`: 指標、除外件数、target/split/確率種別、bin設定、モデルとDatasetの識別情報。
- `predictions.parquet`: 再集計用の馬別予測・教師・ID。NNでは馬番と開催日も保存する。
- `manifest.json`: 予測表・指標JSONを含む出力ファイルのハッシュ。

既定は`--n-bins 10 --strategy quantile`。`--strategy uniform`で等間隔に切り替える。
bin内部境界に一致する値は下側のbinへ入れる。同一確率を分割せず、空binは曲線から除外するため、
点数は指定bin数より少なくなることがある。ヒストグラムは常に確率0〜1の等間隔表示。
Loglossのみ計算上の確率を`[1e-12, 1-1e-12]`へclipし、曲線/Brierでは元の値を使う。

CLI/ファイル入力ではモデル・ParquetのSHA-256、NNではcheckpoint/入力/prepared IDを保存する。
ロード済みオブジェクトのPython入力は`source=in_memory`となり、ファイル由来の同一性は保証しない。
出力は全ファイルを一時領域で完成させてから公開する。既存ディレクトリは上書きしない。

## オッズ帯別評価

オッズは評価用の別入力として扱い、モデルの特徴量には追加しない。
初回に上記のexportで予測を保存し、次の手順でオッズsnapshotを取得する。
以前の`predictions.parquet`がないレポートは、元のモデル・Datasetから一度再出力する必要がある。

```bash
uv run --no-sync python -m pipeline.jobs.prepare_calibration_odds \
  --predictions-report /absolute/path/reports/nn-calibration
```

この準備コマンドだけがDBへ接続する。既存の`TrainingRepositoryPort`を通して対象レースの
発走10分前オッズを取得する。`--minutes-before-start 10 --max-age-seconds 300`が既定。
既存の10分前snapshot用DB Adapterは他の分数を拒否する。
予測表には`race_id`, `horse_number`, `held_date`が必要。`kettonum`がある場合は元datasetとの馬ID一致も検証する。
オッズの欠損・期限切れ・締切不明を残したままParquetとmanifestを保存し、snapshot IDを返す。
保存先は`--odds-root`（既定`pipeline/artifacts/evaluation_odds`）。

取得後は、DBもモデルも使わず帯別レポートを生成できる。

```bash
uv run --no-sync python -m pipeline.jobs.export_calibration \
  --predictions-report /absolute/path/reports/nn-calibration \
  --odds-snapshot-id '<snapshot_id>' \
  --odds-market place --place-method midpoint \
  --output-dir /absolute/path/reports/nn-calibration-odds
```

通常のモデル＋dataset入力にも同じ`--odds-snapshot-id`を追加できる。
Pythonは`export_calibration_report(..., odds=odds_batch)`、または
`reaggregate_calibration_report(predictions_report=..., odds_snapshot_id=..., output_dir=...)`を使う。
再集計は元のsplit・target・確率種別・checkpointを保持し、モデルのロード・推論・fitは行わない。
帯を変えるだけなら`--odds-bounds '1,2,5,10,inf'`を追加する。

### 帯・確率・母集団

- 券種は`--odds-market place|win`。複勝は`--place-method low|high|midpoint|weighted`を選べる。
  既定は複勝の上下限平均。weightedは既存定義の`0.7×low + 0.3×high`。
- 既定帯は`[1,1.4), [1.4,1.8), [1.8,2.5), [2.5,4), [4,7), [7,10), [10,50), [50,inf)`。
  境界値は上側の帯へ入る。カスタム境界も1からinfまでを隙間なく覆う。
- 全体指標はオッズ欠損で変更しない。帯別は選択券種のstatusが`available`かつ教師既知の行だけを使う。
  母集団の利用率・理由別除外数と、同じ利用可能行だけによる全体指標をJSONへ保存する。
- 件数0の帯もCSVに残す。単一クラスのAUCは未定義（空欄）、空帯の誤差指標も空欄。
  全オッズ欠損でも全体評価は残り、帯別の状態は`no_available_odds`となる。
- 帯内のcurveは`min(n_bins, floor(件数/min_samples_per_bin))`を下限1として分割する。
  `--min-samples-per-bin`の既定は30で、分割の目安。30件未満は1点と`small_sample`表示にする。
  同一確率は分割せず、実際の点数はさらに少なくなることがある。
- オッズの発表・利用可能時刻、締切、鮮度は既存のOddsBatch契約を使う。最終オッズへの自動置換はしない。
  `availability_basis=publication_time`の場合、当時の実受信時点までの保証はない。
- LightGBMのDataFrame/ParquetにもID列を含める。`BinaryDataset`は通常IDを持たないため、Pythonで
  `entry_metadata`に同じ行indexの`race_id, horse_number, held_date`（任意で`kettonum`）を渡す。
  結合には行順を使わない。NNは保存DatasetのID対応表を自動利用する。

### 追加ファイル

- `odds_band_metrics.csv`: 頭数・レース数・正例数・平均オッズ・平均予測・実際の的中率・gap・Brier・Logloss・AUC。
  gapは`実績 − 予測`で、正なら過小予測。
- `odds_band_calibration.png`: 帯別curveを同じ軸のパネルで表示。
- `odds_band_bins.csv`: 帯内binの境界・件数・平均予測・実績。
- `metrics.json`の`odds_bands`: 利用率、除外理由、利用可能な同一母集団の指標、snapshot ID・時点規則・帯定義。

帯別のレース数はその帯に馬を含むレース数。同じレースが複数帯に現れるため、レース数は帯を跨いで加算しない。
頭数・正例数は帯別合計が利用可能母集団と一致する。

## 責務と検証

Coreが推論結果の整列・bin/指標計算、UseCaseが評価と保存の手順、Adapterが復元・描画・ファイル公開、
Controller/Jobが実行入口を担当する。NNの通常予測APIには教師列を追加しない。

LightGBMとPyTorchの実行は既存運用どおり別プロセスで検証する。

```bash
uv run --no-sync pytest -q tests/calculations/test_calibration.py \
  tests/calculations/test_odds_calibration.py \
  tests/flows/test_calibration_flow.py tests/integrations/test_calibration_report.py
uv run --no-sync pytest -q tests/calculations/test_nn_transformer.py \
  tests/flows/test_nn_training_flow.py tests/integrations/test_nn_model_store.py
```
