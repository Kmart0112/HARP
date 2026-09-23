# NN Dataset作成

実装範囲は、dbt入力取得または保存入力の読込、開催日による分割、trainだけを使う前処理fit、
レース単位Dataset、NumPyバッチのpadding/mask、再現に必要な入力とrecipeの保存・復元。
このDataset経路はPyTorchなしで利用できる。
後続のネットワーク・学習・保存モデルによる予測は [NN Transformer学習](nn_transformer_training.md) に記載する。
入力表と時点の契約は [NN入力Repository](nn_input_repository_contract.md) を参照する。

## 責務と経路

| 層 | 実装 | 責務 |
|---|---|---|
| Job | `pipeline.jobs.prepare_nn_dataset` | CLI・DB設定解決・Controller・結果出力 |
| Controller | `harp.controllers.nn_dataset` | CommandからQuery/Requestへ変換、同domainのdepsで組立 |
| UseCase | `harp.usecase.nn_dataset` | 入力取得 → Core作成 → 保存、または保存recipeと入力から復元 |
| Core | `harp.core.nn.split` | 開催日によるrace単位分割、教師完備の採用判断 |
| Core | `harp.core.nn.preprocessing` | 数値補完・標準化、カテゴリ辞書、特徴順の照合 |
| Core | `harp.core.nn.dataset` | 馬別履歴参照、1レース1サンプル、batch/mask |
| Port/Adapter | `NnPreparedDatasetStorePort` / `JsonNnPreparedDatasetStore` | 入力ID・前処理・split・Kの保存と読込 |

Core内でSQL、Parquet、JSON、DB接続は扱わない。既存の入力PortとParquet保存を再利用する。
LightGBMのDataset、前処理、学習経路は変更しない。

## 分割と教師

入力Queryの開催日範囲内で、次の閉区間境界を用いる。

- train: `held_date <= train_end_date`
- validation: `train_end_date < held_date <= validation_end_date`
- test: `validation_end_date < held_date`

境界日は必須で、trainの終端はvalidationの終端より前にする。
1レースを複数splitへ分けない。初版の教師は`is_place`。
1頭でも教師がNULLのレースは、全頭をそのsplitの学習・評価用Datasetから除外し、
recipeに`missing_place_label`とレースID・開催日・頭数を残す。
元の入力と`prepared.dataset`は全頭を保持する。学習・評価には必ず`prepared.split(name)`を使う。
新馬や特徴量欠損だけでは除外しない。教師が揃ったtrainレースが0件なら作成を失敗させる。
validation/testが0件の小規模検証は許容し、件数を結果に表示する。

## 前処理

当該Queryで選択されたdbt共通事前特徴を、今回と過去走で使う。
両方に6種類の`*_stats_missing`を加え、今回側に`days_since_last_run`を加える。
過去側だけに当該Queryで選択された過去走結果列を加える。
entity ID、今回結果、絶対run_no、開催日はモデル特徴に含めない。
ID・馬番は配列と予測結果の位置合わせ用metadataとして返す。
許可された事前特徴`horse_number`は特徴としても利用できる。

前処理は今回と過去走で別々にfitする。

- 今回: 採用されたtrainレースの出走行だけ。
- 過去走: そのtrain出走から直近K走として到達できる行の集合だけ。同じ過去走は1回数える。

保存履歴全体にfitしない。validation/testが参照する後の走や、Kから外れた古い走をfitへ入れない。
学習期間より前の過去走も、trainから参照されるならfitに含む。
未取得教師のレースでも、後のtrain出走が参照する過去走としては利用できる。

numericは非欠損値の平均で補完し、母標準偏差で標準化する。
定数列はscale=1、全欠損列はmean=0/scale=1。欠損flagは値と別配列で保持する。
categoricalはtrainで観測した文字列を辞書化する。`0=PAD, 1=UNK, 2=MISSING, 3以降=既知値`。
今回・過去走それぞれの特徴順、mean/scale、辞書はrecipeへ保存する。
推論は保存した前処理でtransformし、特徴名・型・順序の不一致は拒否する。

## Datasetとbatch

`NnRaceDataset`は`__len__`/`__getitem__`を持つmap-style Dataset。
共有する今回・履歴の配列を1回作り、各サンプルで
`history_end_no - K < run_no <= history_end_no`を参照する。
履歴は古い順、実在する走を先頭へ詰め、右側をpaddingする。
全対象出走×Kの配列は常駐させない。split間も同じ配列を共有する。
`collate_nn_races(samples)`でバッチ内の最大頭数までpaddingする。

| 配列 | batch形状 | dtype / 意味 |
|---|---|---|
| `current_numeric` | `[B,N,Fcur_num]` | float32、標準化済み |
| `current_numeric_missing` | 同上 | bool、元の数値欠損 |
| `current_categorical` | `[B,N,Fcur_cat]` | int64、列別embedding用index |
| `history_numeric` | `[B,N,K,Fhist_num]` | float32、標準化済み |
| `history_numeric_missing` | 同上 | bool、元の数値欠損 |
| `history_categorical` | `[B,N,K,Fhist_cat]` | int64、列別embedding用index |
| `history_relative` | `[B,N,K,2]` | float32、後述の相対時間と位置 |
| `entrant_mask` | `[B,N]` | bool、実在出走馬ならTrue |
| `history_mask` | `[B,N,K]` | bool、実在過去走ならTrue |
| `labels` / `label_mask` | `[B,N]` | float32複勝教師 / bool教師既知 |

`history_relative`の列順は`HISTORY_RELATIVE_NAMES`で固定。
`log1p(対象開催日 - 過去開催日の日数)`と`(終端run_no - 過去run_no) / K`。
後者は直近走が0。いずれも固定変換で、validation/testから統計量を学習しない。
maskはすべてTrueが有効。新馬はentrant=True/history全False、競走中止の過去走は
history=True/結果値missing=Trueとなり、架空の走と区別できる。
paddingの値は0、missingflagとlabel_maskはFalseにする。
数値欠損flagをNNへ入力する場合は、trainer側でnumericとの結合などを明示する。

## 保存と復元

```text
pipeline/artifacts/nn_inputs/<input_dataset_id>/
  entries.parquet
  history.parquet
  targets.parquet
  manifest.json
pipeline/artifacts/nn_datasets/<prepared_dataset_id>/
  manifest.json
```

prepared manifestにはversion、教師名、配列配置、相対特徴順、入力ID、K、期間境界、
全レースの分割・除外理由、前処理状態を保持する。manifestのSHA-256がprepared_dataset_id。
一時ディレクトリ内で保存・読込検証してからrenameで公開する。
入力保存後にrecipe公開が失敗した場合、完成済み入力は残り再利用できる。

復元時はrecipeと元Parquet全体のhashを検証し、保存した前処理をそのまま使う。
splitと採用判断を元入力から照合し、DB問合せと再fitはしない。
保存するのは縦持ち入力とrecipeで、padding済み全batchを複製保存しない。
移動時は入力とpreparedの両rootを保管する。元入力が欠けたrecipeだけでは復元できない。

## 実行例

構築済みdbtモデルから取得する。DB設定は既存の`.env`/`HARP_DB_*`を使う。

```bash
uv run --no-sync python -m pipeline.jobs.prepare_nn_dataset \
  --from-date 2015-01-01 --to-date 2026-06-14 \
  --train-end-date 2024-12-31 --validation-end-date 2025-12-31 \
  --history-length 10
```

これは全期間の実行例であり、実行済み結果ではない。小規模な確認には日付範囲を狭める。
`--max-races`は期間内の早いレースから採るため、後ろのsplitが空になり得る。
stdoutには入力ID、prepared ID、split別の採用・除外レース数と頭数をJSONで返す。

既存入力からKや分割を変えて作る。DB設定・特徴契約JSONの再読込は不要。

```bash
uv run --no-sync python -m pipeline.jobs.prepare_nn_dataset \
  --input-dataset-id <input_dataset_id> \
  --train-end-date 2024-12-31 --validation-end-date 2025-12-31 \
  --history-length 20
```

保存済みDatasetをメモリ上へ復元して使う。

```python
from harp.controllers.nn_dataset.controller import NnDatasetController
from harp.core.nn.dataset import NnRaceDataset, collate_nn_races

controller = NnDatasetController("pipeline/artifacts/nn_inputs", "pipeline/artifacts/nn_datasets")
prepared = controller.load("<prepared_dataset_id>")
train = prepared.split("train")
batch = collate_nn_races([train[i] for i in range(min(4, len(train)))])
# NumPy配列から学習frameworkのtensorへの変換は、後続trainerで行う。

# Repository/保存snapshotから取得した推論用NnRaceInputsにも同じ前処理を使う。
# prediction = NnRaceDataset(prediction_inputs, prepared.preprocessing, prepared.config.history_length)
```

## 検証

```bash
uv run --no-sync pytest -q tests/calculations/test_nn_dataset.py \
  tests/flows/test_nn_dataset_flow.py tests/integrations/test_nn_prepared_dataset_store.py
```

公開Datasetの出力、分割・採用、未来値変更に対するfitの不変性、K境界、空履歴、欠損とPAD/UNK、
入力順序と教師の整合、Port経由の作成・復元、保存の往復と依存ファイル破損を確認する。
