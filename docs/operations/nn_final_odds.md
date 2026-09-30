# NN補助教師用の確定複勝オッズ取得

保存済みNN Datasetで採用済みの全出走に、確定複勝オッズを対応付けて保存する。
この処理の成果物は教師用snapshotであり、モデルへの入力特徴量ではない。
モデルの変更、対数変換、標準化、学習はこのJobの責務に含めない。

## 実行

```bash
uv run --no-sync python -m pipeline.jobs.capture_nn_final_odds \
  --prepared-dataset-id <prepared_dataset_id> \
  --output-root pipeline/artifacts/nn_odds
```

`--input-root`と`--prepared-root`は既存の入力・prepared artifactのルート。
日付やレース上限を別指定せず、保存済みpartitionsの`exclusion_reason`がNULLの出走を使う。
train/validation/test、馬番、馬ID、開催日は保存済み入力を正本とする。
特徴量・履歴をDBから取り直さず、分割・前処理も変更しない。

接続情報は既存のruntime設定から解決する。CLI出力はsnapshot ID、元Dataset ID、
頭数、レース数、状態別件数、年×split×状態のcoverageを持つJSON。
`--batch-size`は1～5,000頭で、既定値は5,000。

## 取得元と初回監査

標準の物理bindingは`core.fct_race_entry_final_odds`。
`race_id, horse_number`で照合し、`odds_fukusho_low/high`を論理列`place_low/high`として取得する。
値は既に払戻倍率になっている。`pay_fukusho`や時系列オッズからの代替取得は行わない。
`updated_at`は元テーブルの構築時刻であり、オッズ発表時刻ではない。

DB Adapterは要求キーをVALUESにし、LEFT JOINで欠損行も返す。
全チャンクを同じREAD ONLY / REPEATABLE READトランザクションで読む。
取得列・テーブル名・IDのDB型は`FinalOddsMapping`に閉じ込める。
文字列IDを浮動小数へ変換しない。物理BIGINTへ結ぶ際は、桁落ちなく変換できる正規の整数表記だけを許可する。

標準bindingでは`staging.stg_n_odds_tanpuku`も同じ要求キーで照合する。
確定表とstagingのどちらのキー重複も拒否し、行の存在と下限・上限の一致を確認する。
これにより、確定表のDISTINCT ONで隠れているstaging重複や古い確定表を検出する。
テーブル・必須列の欠落は契約違反であり、全件欠損に読み替えない。

raw→stagingの整合性は初回取得前に別途監査する。
既存stagingは最大race IDより後だけを増分追加するため、過去訂正の反映はこのJobだけでは保証しない。
rawはdbtのsource名`raw`がそのままDBスキーマ名とは限らないため、sources.ymlのbindingに従う。
対象期間でrawとstagingの重複、既存のフィルタ・倍率変換後の値一致、stagingと確定表の値一致を確認する。
既存stagingの除外条件に起因する欠損もsnapshotでは欠損のまま残る。
不一致がある場合は原因と更新範囲を確認してから再構築する。Jobが自動でDBを書き換えることはない。

## 欠損と契約

| status | 意味 |
|---|---|
| available | 上下限が有限かつ1以上、下限≦上限 |
| missing_row | 元の確定表に要求キーの行がない |
| missing_value | 行はあるが上下限の一方以上が欠損 |
| invalid_value | 非有限の倍率、1未満、上下逆転 |

有効性判定は欠損行→欠損値→不正値の順。NaNは欠損値として扱う。
数値列の解釈不能、キー重複、予期しないキー、曖昧な時刻のtimezoneは処理を失敗させる。
欠損・不正値で馬を削除せず、その元の値と状態を保存する。
trainのavailableが0件ならsnapshotを公開せず失敗する。
下限・上限だけを用いる教師変換やmask生成は後段で行う。

## 保存と復元

```text
<output-root>/<snapshot_id>/
  odds.parquet
  coverage.csv
  manifest.json
```

odds.parquetは次の論理列を持つ。

```text
race_id, kettonum, horse_number, held_date, split
place_low, place_high, source_found, source_updated_at, status
```

`source_found`は欠損行と欠損値を区別するためのbool。
行はrace ID・馬番の順に保存し、教師を取り出す際は行番号でなくキーで対応付ける。
時刻はtimezone付きUTC、開催日はtimezoneなしの日付、IDは文字列で保存する。
CoreのDataFrameプロパティは防御的コピーを返す。

manifest version=1、kind=`nn_final_place_odds`、usage=`auxiliary_target`。
元のprepared/input Dataset ID、対象キー・馬ID・日付・splitのハッシュ、取得時刻、
物理mappingとその識別用ハッシュ、staging照合の有無、状態別件数、ファイルのSHA-256と行数を保持する。
mappingのrevisionはDBデータ世代ではない。実際に捕捉した値はParquetのハッシュで識別する。
snapshot IDはmanifestのSHA-256。取得時刻も含むため、DB再取得では別IDになる場合がある。

一時ディレクトリへ書き、全ファイルを読み戻して検証してからrenameで公開する。
復元時はversion/kind/usage、全ファイルのハッシュ、行数、キー、元値とstatus、coverageを再検証する。
復元はDB接続もモデル実行も必要としない。

```python
from harp.adapters.driven.storage.nn_odds_snapshot_store import ParquetNnOddsSnapshotStore

snapshot = ParquetNnOddsSnapshotStore("pipeline/artifacts/nn_odds").load(snapshot_id)
teachers = snapshot.frame
coverage = snapshot.coverage
```

後段で別Datasetと組み合わせる前には、prepared/input Dataset IDと
`nn_odds_reference_hash(reference)`をsnapshotの`entry_keys_sha256`へ照合する。
既存NN入力契約、既存targets.parquet、prepared manifestはこの取得処理では変更しない。

## オッズheadの学習

学習時に`--odds-snapshot-id`で教師snapshotを指定する。入力Datasetは作り直さず、
prepared/input IDと対象キー・馬ID・日付・splitのハッシュ一致を確認して結合する。

```bash
uv run --no-sync python -m pipeline.jobs.run_nn_train \
  --dataset-id <prepared_dataset_id> \
  --odds-snapshot-id <snapshot_id> \
  --recipe pipeline/config/nn_training/place_history_set_odds.yml \
  --model-root pipeline/artifacts/nn_training/place-odds/models
```

`--odds-root`の既定値は`pipeline/artifacts/nn_odds`。
比較用の`place_history_set_no_aux.yml`は同じNN・seed・学習条件で補助headを持たない。
どちらも着順headを持たず、同じsnapshotを指定できる。

教師は`log((place_low + place_high) / 2)`。availableなtrain出走だけで平均と母標準偏差を
計算して標準化する。分散0ならscale=1。平均・scale・train件数・snapshot ID・キーの
ハッシュはrun metadataとcheckpointへ保存し、評価時は保存値で変換する。
missing/invalidな教師は0とmask=Falseにして、複勝ラベルと出走集合を維持する。

共有表現から1次元のオッズheadを出し、標準化した対数教師にdelta=1のHuber lossを使う。
総lossは複勝BCE + 0.1 × odds Huber。各batchの有効なオッズ教師数で平均し、
教師がないbatchの補助lossは0とする。head初期化は主タスクの乱数列を変えない。
`odds_huber`、未標準化の対数空間でのMAE/RMSE、有効教師数を記録する。
複勝logloss・AUC・Brierはオッズ欠損も含む全対象で計算する。

epoch選択・学習率調整・early stoppingは主タスクのvalidation.loglossだけを使う。
推論時に確定オッズやsnapshotは不要で、モデル入力にも教師値を含めない。
主タスク予測・calibration exportは保存モデルと既存Datasetだけで実行できる。
補助head自体の精度評価には、指定した`odds_root`に保存snapshotが必要。
resumeは教師snapshot・標準化・レシピ・実行環境が一致した場合だけ許可する。

## 検証

Coreの欠損判定とキー照合、UseCaseの既存分割保持・失敗時の非公開、
SQLの公開Port（改名・追加列・数値/文字列型・大きなID・欠損・重複・staging不一致）、
snapshotの往復・改ざん検知を検証する。

```bash
uv run --no-sync pytest -q tests/calculations/test_nn_odds_targets.py \
  tests/flows/test_nn_final_odds_flow.py tests/integrations/test_nn_final_odds_ports.py
```

`HARP_CONTRACT_TEST_DB_URL`が指定されるとSQLiteに加えてPostgreSQLでもPort契約を実行する。
PostgreSQLテストは実行ごとの専用schemaを作成・削除し、既存の業務テーブルへ書き込まない。
