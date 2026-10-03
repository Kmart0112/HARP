# NN Transformer学習

実装は`history_set_transformer_v1`と`history_conditioned_set_transformer_v1`。馬ごとの過去走をTransformerで集約し、
今回特徴と結合した後、出走馬全体を別のTransformerへ渡して各馬のlogitを出す。
`task=place/win`で複勝・勝率を切り替え、Datasetのtaskと学習recipeのtaskが違う場合は学習を拒否する。
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

`forward()`は`[B,N]`のlogitを返す。複勝は各馬にsigmoid、勝率は実出走馬のレース内softmaxを適用する。
勝率ではPADのlogitを負の無限大へ置換し、PADへ確率を割り当てない。学習・評価は単独勝者のレースだけを使う。

### 今回特徴で条件付けた履歴集約

`history_conditioned_set_transformer_v1`は、Current Encoderの出力`c`を
既存の学習可能な集約トークン`t`へ加算してから履歴Transformerへ渡す。

```text
c = CurrentEncoder(今回の数値・欠損flag・カテゴリ)
h = HistoryEncoder(各過去走の特徴・欠損flag・相対日数/走順)
tokens = concat([(t + c)], h)             # 馬ごとに [K+1, D]
summary = HistoryTransformer(tokens)[:, 0]
horse = Fusion(concat(c, summary))       # [2D] → [D]
logit = Head(RaceTransformer(horse))
```

- 今回の距離・芝ダート・馬場等に加え、現在の馬・騎手に関する既存の事前特徴全体を使う。
  `time_vs_avg`・`pos4_agari_synergy`・相手集約は引き続き各過去走の入力であり、今回の結果は使わない。
- `[t+c, h_1, ..., h_K]`のSelf-Attentionで、先頭トークンのQueryが今回特徴に依存する。
  Key/Valueには先頭トークン自身も含まれる。同条件の過去走へ高い重みを付ける規則は固定しない。
- 集約トークンは常に有効。履歴0走でも今回特徴を含むトークンで計算し、全maskのAttentionを作らない。
  履歴PAD・出走馬PADの無効化、出走馬の並べ替えに対する性質は共通実装を使う。
- 追加の学習パラメータや乱数消費はない。同じ入力次元・recipeのseedで初期重みが一致する。
  Current Encoderへは履歴集約と最終結合の両経路から勾配が流れる。
- モデル名は保存recipeから学習・推論ともに復元する。既存名は`t`だけを使う従来計算を維持する。
  重みの形が同じでもモデル名は意味が異なり、モデル名を変更した途中再開は拒否する。
  保存済みprepared Datasetを再利用でき、dbt・特徴契約・前処理の変更は不要。

## 複勝への着順補助タスク

`pipeline/config/nn_training/place_history_set_rank.yml`は`version: 2, task: place`のrecipe。
主損失は既存の頭数平均BCE、補助損失はレース平均のpairwise logisticとする。
出走馬Transformerの表現を共有し、既存の複勝headとは別に線形の順位headを置く。
順位スコアが大きい馬ほど先着しやすい。`forward()`の戻り値と公開予測の`place_probability`は維持する。
学習と順位診断は`forward_outputs()`で両headを一度のTransformer計算から得る。

- 教師は保存済み`targets.result_order`。Datasetが`finish_order/finish_order_mask`として渡す。
  今回の着順は`NnModelInputs`に含めない。既存snapshot・prepared ID・前処理を再利用できる。
- 同じレースの既知着順`r_i < r_j`ごとに`softplus(-(s_i - s_j))`を計算し、各ペアを一度だけ数える。
  ペアをレース内で平均し、比較ペアなしのレースを0として全レースで平均する。
- 同着馬同士、未知着順、PADのペアは除外する。1着同着を含めて複勝Datasetの既存採用条件を維持する。
  結果0を最下位へ置換しない。Repositoryで主教師もNULLとなるレースは従来どおり全体を除外する。
- `L = entrant_mean_BCE + auxiliary_rank.weight * race_mean_rank_loss`。
  補助あり/なしで主タスクの集約単位を変えない。初版の順位補助は複勝のみで利用可能。
- `auxiliary_rank`には`name: pairwise_logistic`、非負の`weight`、`reduction: race_mean`、
  `tie_policy: ignore`を指定する。旧version 1 recipeは補助なしとして復元する。
- `weight: 0`は同じ構成の比較対照。順位headの初期化で共有部・dropoutの乱数列を進めず、
  重み0では順位勾配を逆伝播しない。主タスクだけの既存学習と予測が一致することを検証する。
- best選択・early stopping・schedulerは複勝の`validation.logloss`だけを使う。
  `rank_loss`、`rank_pair_accuracy`、`rank_pairs`、`rank_races`を別途記録する。
  先着正解率は比較可能レースの平均で予測同値を0.5点とする。有効ペア0のとき順位指標は未定義。
  trainの`total_loss`はepochの各損失をそれぞれの母数で集約してから再結合する。
- recipeと両headをcheckpointへ保存し、推論・明示評価・校正レポートで同じ構成を復元する。
  補助重みを変更したrunの途中再開は拒否する。

同じprepared Datasetに対して、上記recipeと`--set auxiliary_rank.weight=0`を比較する。
特徴・対象レース・seed・学習予算を揃え、validationで判断してから固定した設定をtestへ適用する。
順位損失の改善だけでは複勝予測の改善と判断しない。

## 設定

複勝のデフォルトは`pipeline/config/nn_training/place_history_set_no_aux.yml`。
直近の比較実験と同じD=32、履歴1層、全頭2層、最大30epochの構成で、
`auxiliary_rank: null`と`auxiliary_odds: null`により両補助headを生成しない。
`--recipe`を省略するとこの設定を使う。
条件付き履歴集約は`pipeline/config/nn_training/place_history_conditioned_no_aux.yml`を明示して使う。
モデル名以外は通常の補助なしrecipeと同じD=32、4heads（各8次元）、履歴1層、全頭2層、
FFN=64、dropout=0.1とし、同じprepared Dataset・seed・学習予算で比較する。

```bash
uv run --no-sync python -m pipeline.jobs.run_nn_train \
  --dataset-id <place_prepared_dataset_id> \
  --recipe pipeline/config/nn_training/place_history_conditioned_no_aux.yml
```

勝率の正本は`pipeline/config/nn_training/win_history_set_v1.yml`（D=32、履歴1層、全頭2層、最大30epoch）。
taskが省略された既存recipe・モデルは複勝として読み込む。勝率recipeは`task: win`、
`loss.name: cross_entropy`、`loss.reduction: race_mean`を指定する。

勝率用のDataset作成・学習例（入力snapshotと年境界を明示する）:

```bash
uv run --no-sync python -m pipeline.jobs.prepare_nn_dataset \
  --input-dataset-id <input_dataset_id> --task win --history-length 10 \
  --train-end-date 2023-12-31 --validation-end-date 2024-12-31

uv run --no-sync python -m pipeline.jobs.run_nn_train \
  --dataset-id <win_prepared_dataset_id> \
  --recipe pipeline/config/nn_training/win_history_set_v1.yml
```
同じチューニング値をPythonのデフォルトにも重複させない。

| セクション | 値 |
|---|---|
| model | architecture、内部次元、Embedding次元、層数、head数、FFN次元、dropout |
| optimizer | AdamWのlr、weight_decay |
| scheduler | validation loglossによるReduceLROnPlateauのfactor/patience/min_lr |
| training | レース単位batch size、max_epochs、seed、gradient clipping |
| loss | 複勝: BCE with logits / entrant_mean、勝率: cross_entropy / race_mean |
| early_stopping | validation.logloss、min、patience、min_delta |
| runtime | auto/cpu/mps/cuda、float32、num_workers、num_threads |

CLIで`--set section.field=value`を指定した値だけYAMLへ上書きする。
数値・bool等はJSONリテラルとして解析し、`runtime.device=cpu`のような名前は文字列になる。
未知キー、重複YAMLキー、重複override、必須値の欠落、無効な範囲、D/head数の不整合は拒否する。
architecture・optimizer・loss・選択指標・精度は上記のみをサポートする。

勝率では`logloss`は勝ち馬に対する負の対数確率のレース平均で、モデル選択・schedulerにも使う。
`top1_accuracy`は予測最大の馬が勝ったレースの割合、`race_brier`はレース内二乗誤差の合計のレース平均。
`auc`、`brier`、`binary_logloss`は全評価馬をまとめた二値指標で、レース単位Log lossとは別。
確率が同値のときのtop1はDatasetの馬順で先の馬を選ぶ。
複勝と勝率のLog lossは教師・集約単位が異なるため、値を直接比較しない。

特徴数、カテゴリ数はDatasetから自動決定し、YAMLには書かない。
過去走の相手集約も`history_numeric`へ入る。`history_set_transformer_v1`のEncoderが
前処理から増加した入力次元を決めるため、新しいネットワーク名・相手用の配列軸は設けない。
相手情報ありのDatasetは別IDとして新規学習し、旧重みへ列を継ぎ足して再開しない。
旧Dataset・旧モデルは元の特徴次元で復元でき、特徴順が違う入力での予測は拒否する。
K・期間分割・特徴契約・前処理はprepared Dataset側で固定する。変更時はDatasetを再作成して別IDを渡す。
device=autoはCUDA→MPS→CPUの順に利用可能なものを選び、解決後のdeviceも保存する。

## 学習・評価

1. 保存入力とrecipeのhash・契約を検証してDatasetを復元する。
2. train/validation両方が空でないことを確認する。
3. seedを設定し、ネットワーク・AdamW・schedulerを初期化する。
4. レース単位でshuffleし、全頭をまとめて1epoch学習する。
5. `eval()`・`inference_mode()`でvalidationを評価する。
6. best判定、early stopping、scheduler更新、checkpoint保存、任意のtrackingを行う。

複勝損失は`entrant_mask & label_mask`の位置だけで平均する。勝率損失は実出走馬内の勝ち馬の交差エントロピーをレース平均する。
PADや未知教師を負例にしない。
学習入力はレースの全教師が揃っていることを再確認する。
epochのloglossは複勝では有効頭数、勝率では有効レース数で重み付けする。Brier/AUCも記録し、単一クラスのAUCは未定義扱い。
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
予測に学習入力全体は不要。出力は`race_id, kettonum, place_probability`または`win_probability`。
taskはモデルmetadata・recipeとDatasetへ保存し、復元・推論・校正レポートでも照合する。
オッズ・校正・EV・購入判断はこの経路に含まない。

## 実行

```bash
uv sync --locked --extra nn

uv run --no-sync python -m pipeline.jobs.run_nn_train \
  --dataset-id "<prepared_dataset_id>" \
  --recipe pipeline/config/nn_training/place_history_set_no_aux.yml
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
  tests/calculations/test_nn_win_transformer.py tests/flows/test_nn_training_flow.py \
  tests/integrations/test_nn_model_store.py tests/integrations/test_nn_win_model_store.py
```

順位補助の検証は`tests/calculations/test_nn_rank_auxiliary.py`、
`tests/flows/test_nn_rank_training_flow.py`、`tests/integrations/test_nn_rank_model_store.py`を
同じNN専用プロセスへ加える。

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
  --ignore=tests/calculations/test_nn_win_transformer.py \
  --ignore=tests/flows/test_nn_training_flow.py \
  --ignore=tests/integrations/test_nn_model_store.py \
  --ignore=tests/integrations/test_nn_win_model_store.py \
  --ignore=tests/calculations/test_nn_rank_auxiliary.py \
  --ignore=tests/flows/test_nn_rank_training_flow.py \
  --ignore=tests/integrations/test_nn_rank_model_store.py
```
