# NN Transformer学習

実装は`history_set_transformer_v1`。馬ごとの過去走をTransformerで集約し、
今回特徴と結合した後、出走馬全体を別のTransformerへ渡して各馬の複勝logitを出す。
[作成済みDataset](nn_dataset_preparation.md)を復元して学習し、DB問合せや前処理の再fitはしない。

## 配置と責務

| 層 | 実装 | 責務 |
|---|---|---|
| Core | `core/nn/config.py` | 型付き設定、許可する構成、明示overrideと値の検証 |
| Core | `core/nn/tensor_batch.py` | Datasetから入力次元を決定、NumPy→Tensor、特徴と教師・IDの分離 |
| Core | `core/nn/networks/` | FeatureEncoder、履歴Transformer、出走馬Transformer、logit出力 |
| Core | `core/nn/losses.py` | 有効出走・既知教師に対するBCE |
| Core | `core/nn/training.py` | 初期化、1epoch学習、評価、選択、checkpointの状態化・復元 |
| Core | `core/nn/prediction.py` | 保存前処理による入力変換と確率出力 |
| UseCase | `usecase/training/nn.py` | Dataset復元、epoch進行、保存・tracking、独立した評価手順 |
| UseCase | `usecase/prediction/nn.py` | Port経由で保存モデルを復元 |
| Controller | `controllers/training/nn.py` | YAML/CLIからRequestを作り、deviceを解決 |
| Composition | `controllers/training/deps.py` | NN用Adapter生成、device能力の確認 |
| Port | `nn_training_ports.py` | YAML読込とcheckpoint保存・復元の契約 |
| Adapter | `storage/nn_training_recipe.py` | YAML/CLI値の構文解析 |
| Adapter | `storage/nn_model_store.py` | torch/JSON保存、hash検証、atomic公開 |
| Job | `pipeline/jobs/run_nn_train.py` | 学習の実行入口 |
| Job | `pipeline/jobs/evaluate_nn_model.py` | 確定済みモデルの明示評価入口 |

CoreにSQL・ファイルI/O・MLflowを入れない。既存の`TrackingPort`と複勝評価指標を利用する。
PyTorchは`nn` extra。既存LightGBMやDataset作成の入口からはNNネットワークをimportしない。

## ネットワーク

```text
過去走の数値 + 欠損flag + カテゴリEmbedding + 相対日数/走順
  → FeatureEncoder → 履歴Transformer → 集約トークン
今回の数値 + 欠損flag + カテゴリEmbedding
  → FeatureEncoder
両者を連結 → Linear/LayerNorm/GELU
  → 出走馬Transformer → Linear → 各馬のlogit
```

- 初期recipeはD=128、履歴2層、出走馬2層、4heads、FFN=256、dropout=0.1。
- 今回と過去走は前処理辞書が別なのでEmbeddingも別にする。カテゴリ0はPAD。
- 各履歴に常に有効な学習可能な集約トークンを置く。新馬はそのトークンだけで履歴表現を作る。
- 履歴は対象日より前の走のみ。履歴内は双方向Attentionとし、既存の相対日数・走順を使う。
- 出走馬の配列位置を表すEmbeddingは付けない。馬と特徴を並べ替えると予測も同じ順で並べ替わる。
- 実在する馬だけをFeatureEncoderへ入れる。履歴PADはEmbedding参照前に0へ置換する。
- DatasetのTrue=有効を、PyTorchのkey padding maskへ渡す際に反転する。無効queryの表現も各層で0へ戻す。
- Transformerの各層は個別に生成・初期化する。全馬・全レースでEncoderの重みを共有する。
- `NnModelInputs`に教師・馬ID・レースIDは含めない。ネットワークへ渡す特徴と位置合わせ情報を分離する。

`forward()`は`[B,N]`のlogitを返す。確率出力時だけsigmoidを適用する。
複勝は複数頭が正例になるので出走馬全体へのsoftmaxは使わない。

## 設定

正本は`pipeline/config/nn_training/place_history_set_v1.yml`。
同じチューニング値をPythonのデフォルトにも重複させない。

| セクション | 値 |
|---|---|
| model | architecture、内部次元、Embedding次元、層数、head数、FFN次元、dropout |
| optimizer | AdamWのlr、weight_decay |
| scheduler | validation loglossによるReduceLROnPlateauのfactor/patience/min_lr |
| training | レース単位batch size、max_epochs、seed、gradient clipping |
| loss | BCE with logits / entrant_mean |
| early_stopping | validation.logloss、min、patience、min_delta |
| runtime | auto/cpu/mps/cuda、float32、num_workers、num_threads |

CLIで`--set section.field=value`を指定した値だけYAMLへ上書きする。
数値・bool等はJSONリテラルとして解析し、`runtime.device=cpu`のような名前は文字列になる。
未知キー、重複YAMLキー、重複override、必須値の欠落、無効な範囲、D/head数の不整合は拒否する。
初版のarchitecture・optimizer・loss・選択指標・精度は上記のみをサポートする。

特徴数、カテゴリ数はDatasetから自動決定し、YAMLには書かない。
K・期間分割・特徴契約・前処理はprepared Dataset側で固定する。変更時はDatasetを再作成して別IDを渡す。
device=autoはCUDA→MPS→CPUの順に利用可能なものを選び、解決後のdeviceも保存する。

## 学習・評価

1. 保存入力とrecipeのhash・契約を検証してDatasetを復元する。
2. train/validation両方が空でないことを確認する。
3. seedを設定し、ネットワーク・AdamW・schedulerを初期化する。
4. レース単位でshuffleし、全頭をまとめて1epoch学習する。
5. `eval()`・`inference_mode()`でvalidationを評価する。
6. best判定、early stopping、scheduler更新、checkpoint保存、任意のtrackingを行う。

損失は`entrant_mask & label_mask`の位置だけで平均する。PADや未知教師を負例にしない。
学習入力はレースの全教師が揃っていることを再確認する。
epochのloglossは損失総和/有効頭数で集計する。Brier/AUCも記録し、単一クラスのAUCは未定義扱い。
非有限logit・勾配・validation loglossは失敗とする。

bestモデルは最小validation loglossで更新する。停止のpatienceは`min_delta`以上の改善がないepochを数える。
best保存とpatienceリセットを分けるので、小さな改善でも最小lossの重みを保存する。
学習UseCaseはtestを評価しない。`evaluate_nn_model`で保存bestモデルを明示的に評価する。
評価は指標JSONをstdoutへ返し、学習や前処理fit、モデル選択を行わない。

## 保存・再開

```text
pipeline/artifacts/nn_training/<run_id>/
  run.json
  latest.json
  checkpoints/<checkpoint_id>/
    best_weights.pt
    last_checkpoint.pt
    metadata.json
    metrics.json
    manifest.json
```

checkpoint_idはmanifestのSHA-256。各epochはimmutableなディレクトリへ保存し、
一時領域で読込検証→rename→latest pointer置換の順で公開する。
書込失敗時は最後の完成済みcheckpointから再開できる。
全checkpointを残すため、長期運用の保存世代削除は別の運用として行う。

- best_weights: 最小validation loglossのCPU `state_dict`。
- last_checkpoint: 最終epochのmodel/optimizer/scheduler、epoch/global_step、bestと停止状態、TorchのCPU/使用deviceの乱数状態、指標履歴。
- metadata: 解決済みrecipe、入力仕様、前処理、K、入力ID・prepared ID、分割集計、元特徴契約、source/capture情報、使用device、親run/checkpoint。
- provenance: Git revision、ソース・設定のfingerprint、Python/OS/Torch/NumPy/pandas version。`.env`やデータファイルはfingerprintへ含めない。

読込はすべてのファイルhashを検証してから`torch.load(weights_only=True, map_location="cpu")`を使う。
前処理と入力仕様の一致も照合する。モデル全体のpickle保存は使わない。

再開はepoch境界に限定し、新しいrunへ分岐する。prepared Dataset、設定、解決device、provenanceは同じものを要求する。
変更できるのは`training.max_epochs`だけで、完了epochより大きくする。
停止済みのearly stoppingを解除して再開することはしない。
shuffle順はseed+epochから決まり、dropout用の乱数状態とoptimizer状態はcheckpointから復元する。
異なるハードウェア間のbit単位一致は保証しない。CPUの同一環境では中断なし学習との一致をテストする。

予測は`load_nn_predictor`でモデルと前処理を復元し、`NnPredictor.predict(NnRaceInputs)`を使う。
予測に学習入力全体は不要。出力は`race_id, kettonum, place_probability`。
オッズ・校正・EV・購入判断はこの経路に含まない。

## 実行

```bash
uv sync --locked --extra nn

uv run --no-sync python -m pipeline.jobs.run_nn_train \
  --dataset-id "<prepared_dataset_id>" \
  --recipe pipeline/config/nn_training/place_history_set_v1.yml
```

短い動作確認は、同じ入口へ明示overrideを渡す。

```bash
uv run --no-sync python -m pipeline.jobs.run_nn_train \
  --dataset-id "<prepared_dataset_id>" \
  --set training.max_epochs=2 \
  --set runtime.device=cpu
```

再開時は元のoverrideも維持する。

```bash
uv run --no-sync python -m pipeline.jobs.run_nn_train \
  --dataset-id "<prepared_dataset_id>" --resume-run-id "<run_id>" \
  --set training.max_epochs=3 --set runtime.device=cpu

uv run --no-sync python -m pipeline.jobs.evaluate_nn_model \
  --run-id "<run_id>" --split test --device cpu
```

`--input-root` / `--prepared-root` / `--model-root`で保存先を指定できる。
通常はDB接続設定不要。`--tracking`を明示したときだけ、既存の`HARP_MLFLOW_TRACKING_URI`と
`HARP_NN_TRAIN_EXPERIMENT`（未指定時`nn_place_training`）を使う。
MLflowにはepoch指標、実効設定、checkpoint参照、終了時のモデルbundleを保存する。
ローカルのcheckpointはtrackingを使わなくても保存する。CLIの最終出力はrun/checkpoint IDと学習結果のJSON。

## 検証

```bash
uv run --no-sync pytest -q tests/calculations/test_nn_transformer.py \
  tests/flows/test_nn_training_flow.py tests/integrations/test_nn_model_store.py
```

馬の並べ替え、padding増加と無効値の不変性、新馬の有限値・勾配、微小Datasetの学習、
batchサイズが異なる評価の整合、dropoutありの再開、test教師の非干渉、early stopping、
設定不一致の拒否、保存失敗、破損検知、前処理込みのモデル復元を公開境界から確認する。
NN extra未導入の環境ではNN学習テストをskipし、CIはextraを導入して実行する。

macOSではPyTorchをimportした後のLightGBM学習がOpenMP競合でsegfaultになる環境がある
（[LightGBM issue #6595](https://github.com/lightgbm-org/LightGBM/issues/6595)）。
HARPでもPyTorch 2.14.0 / LightGBM 4.6.0で再現したため、両者の学習は別のCLIプロセスで実行する。
CIも既存テストと上記NN学習テストを別プロセスへ分ける。ローカルで既存テストを確認するときは以下を使う。
同一プロセス内で両フレームワークを学習させる互換性は保証しない。

```bash
uv run --no-sync pytest -q \
  --ignore=tests/calculations/test_nn_transformer.py \
  --ignore=tests/flows/test_nn_training_flow.py \
  --ignore=tests/integrations/test_nn_model_store.py
```
