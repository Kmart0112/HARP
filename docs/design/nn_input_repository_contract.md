# NN入力Repositoryと保存の契約

本書の対象は契約型、Port、DB入力Repository、特徴契約の読込、入力の保存・復元。
この入力を使うDatasetの配列化、前処理、作成・復元の実行経路は
[NN Dataset作成](nn_dataset_preparation.md)に実装済みの契約を記載する。
後続の学習経路は [NN Transformer学習](nn_transformer_training.md) を参照する。
dbt側の粒度・時点は [nn_race_history_inputs.md](nn_race_history_inputs.md) を正本とする。

## 公開境界

| 層 | モジュール | 責務 |
|---|---|---|
| Core | `harp.core.nn.contracts` | `NnFeatureContract`、`NnInputQuery`、`NnRaceInputs`、`NnTrainingInputs`と値・参照関係の検証 |
| Port | `harp.interface.ports.nn_input_ports` | `NnInputRepositoryPort`、`NnFeatureContractPort` |
| Port | `harp.interface.ports.nn_storage_ports` | `NnDatasetStorePort`、`NnPredictionSnapshotPort` |
| DB Adapter | `harp.adapters.driven.db.nn_input_repository` | `SqlNnInputRepository`、物理名を保持する`NnInputMapping` |
| Storage Adapter | `harp.adapters.driven.storage.nn_feature_contract` | `JsonNnFeatureContractReader` |
| Storage Adapter | `harp.adapters.driven.storage.nn_dataset_store` | `ParquetNnDatasetStore`、`ParquetNnPredictionSnapshotStore` |

CoreはDBやファイルを読まない。NN inputの取得・保存にはPyTorchを必要としない。
既存LightGBM用の`RaceInputs`、Repository、保存形式は変更しない。

```text
load_training_inputs(query)   -> NnTrainingInputs(inputs, targets)
load_prediction_inputs(query) -> NnRaceInputs(entries, history)
```

Queryは開催日の閉区間、事前特徴、過去走結果の選択、最大レース数を持つ。
物理テーブル名・SQL・任意の行フィルタはQueryに含めない。
最大レース数は開催日・レースIDの昇順で適用し、レース途中で出走馬を切らない。

## 入力の粒度と保持範囲

- `entries`: 今回出走を1行とする。キーは`race_id, kettonum`。
- `history`: 対象馬ごとに、今回出走群の最大`history_end_no`までの完全な履歴prefixを1回だけ保持する。
- `targets`: 学習用に限り、全出走キーに対応する`result_order, is_win, is_place`を持つ。

同じ過去走を複数の対象出走が参照しても、history行を複製しない。
historyは後の対象出走が使う結果も含むため、各出走で利用する範囲は必ずその行の
`history_end_no`以下に制限する。保存段階では直近K走へ切らず、Kを変えても同じ入力を利用できる。
馬・レースIDは管理用の文字列へ正規化し、浮動小数IDを拒否する。欠損付き整数IDもfloatへ変換しない。

新馬、欠損統計、競走中止を含む過去走を保持する。オッズとの結合は行わない。
今回の出走集合はdbt側の非出走除外後の集合を使い、全頭数との一致を検証する。
結果の内部結合で馬を削除せず、未取得教師はNULLとして保持する。
教師未取得の採用判断や、異常走へのラベル補完はこの層では行わない。
推論用メソッドは今回の教師テーブルを参照しない。

既存のoutcome martは`result_order=0`に対しても`<=3`等で複勝Trueを返す場合がある。
NN Repositoryでは着順0を未確定値として`result_order/is_win/is_place`をすべてNULLへ変換する。
過去走の着順0もNULLへ変換する。出走自体は残し、Dataset側で教師完備を判断する。
元martや既存LightGBMの教師定義は、このNN Adapterの変換では変更しない。

入力の値はnumeric/categoryへ正規化するが、補完・標準化・カテゴリ辞書の学習は行わない。
NULLと0を区別し、無限大や数値でないnumeric値は拒否する。
DataFrameの取得プロパティは防御的コピーを返す。

## 時点と更新

dbtの履歴表と対象出走表をともに構築し終えてから取得する。
PostgreSQLでは一つのREAD ONLY / REPEATABLE READトランザクションで今回出走、履歴、教師を読む。
SQLiteの契約テストでも複数SELECTを一つの明示トランザクションに置く。

RepositoryはDB上の「対象日より前の最大run_no」と参照終端を照合する。
Coreでも、履歴の連番・開催日順、参照終端のレースID・開催日・間隔、全頭数を照合する。
履歴バックフィル後に対象出走表を再構築していないなどの不一致は`NnInputContractError`とする。

統計参照日がNULLの行は、対象の主体群がすべて`stats_missing=True`で、
対応する統計特徴がNULL（出走母数だけは0も可）の場合に限り受け入れる。
月次は騎手・種牡馬・母・母父、年次は厩舎・生産者が対象。
参照日を開催日から推測して補完せず、NULLのまま保存・復元する。
参照日不明で複勝率や正の出走母数などが入っている行は拒否する。

トランザクションだけで、別々に公開されるdbtモデルが同じ更新世代に属することまでは証明できない。
NNのdbt構築完了後に取得する運用が前提。保存後はDB更新から独立して再実行できる。

`captured_at`は取得時刻、`source_revision`は物理mappingの識別用ハッシュであり、
過去の発表・受信時刻やデータ世代番号ではない。manifestには`availability_basis=event_date`を記録する。
過去の発走直前の入力状態を復元した、という意味ではない。

## 保存形式

保存先は明示的に与え、環境変数をAdapter内で読まない。

```text
<root>/<dataset_id>/
  entries.parquet
  history.parquet
  targets.parquet       # 学習入力のみ
  manifest.json
```

manifestには保存形式version、training/predictionの種別、Query、順序付き特徴契約、
source_revision、captured_at、呼出元metadata、各ファイルのSHA-256と行数を含む。
manifestのSHA-256をdataset_id / snapshot_idとする。

一時ディレクトリへ書き、読込・契約検証を行ってからrenameで公開する。
復元時はversion、種別、全ファイルのハッシュと行数、値と履歴参照の契約を検証する。
学習用と推論用の保存入力は取り違えて読み込めない。復元時にDBは読まない。
推論snapshot v1はNN入力のみで、オッズ・EV・予測結果は含まない。

## 利用例

以下はAdapterを組み合わせる利用例。Datasetまで作成する正式な実行Jobは
`pipeline.jobs.prepare_nn_dataset`を使う。
engineは呼出元で接続情報を解決して生成する。

```python
from harp.core.nn.contracts import NnInputQuery
from harp.adapters.driven.db.nn_input_repository import NnInputMapping, SqlNnInputRepository
from harp.adapters.driven.storage.nn_feature_contract import JsonNnFeatureContractReader
from harp.adapters.driven.storage.nn_dataset_store import ParquetNnDatasetStore

contract = JsonNnFeatureContractReader().load("pipeline/config/nn_input_contract.json")
repo = SqlNnInputRepository(engine=engine, mapping=NnInputMapping(), contract=contract)
query = NnInputQuery(
    from_date="2026-06-13", to_date="2026-06-14",
    feature_names=contract.pre_race_names,
    history_result_names=contract.history_result_names,
    max_races=20,
)
inputs = repo.load_training_inputs(query)
store = ParquetNnDatasetStore("pipeline/artifacts/nn_inputs")
dataset_id = store.save(inputs, {"purpose": "initial NN dataset"})
restored = store.load(dataset_id)
```

## 特徴契約の生成

`pipeline/config/nn_input_contract.json`はdbt macroの出力を保存した生成物。
59個の事前特徴名は`nn_pre_race_feature_columns()`を正本とし、Python側へ手で追加しない。
特徴追加時はmacroから再出力し、契約JSONも同時に更新する。

```bash
scripts/dbt run-operation export_nn_input_contract \
  --project-dir dbt/harp --profiles-dir dbt/harp --no-version-check \
  --log-format json > /tmp/harp-nn-contract-export.jsonl
```

JSONログのうち、`info.msg`が`version, pre_race, history_results`を持つJSONオブジェクトの
イベントを1件取り出し、そのオブジェクトを整形して契約JSONへ保存する。
Readerは未知version、重複列、今回特徴への結果・識別子混入を拒否する。

## 検証

```bash
uv run --no-sync pytest -q tests/calculations/test_nn_input_contract.py \
  tests/integrations/test_nn_input_port_contract.py \
  tests/integrations/test_nn_storage_port.py
```

`HARP_CONTRACT_TEST_DB_URL`があればSQLiteに加えてPostgreSQLの専用一時schemaでも検証する。
改名・列追加・数値型差、全頭保持、教師欠損、同日・未来除外、参照番号ずれ、欠損付き大整数ID、
保存の往復と破損検知を公開契約から確認する。学習品質やNNの動作はこの検証の対象外。
