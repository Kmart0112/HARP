# HARP Hexagonal責務分離（実装準拠・正本）

## 0. 目的と適用範囲

- 本書は、HARP の現行実装に基づく Hexagonal Architecture の責務分離を定義する正本である。
- 対象は `pipeline`、`src/harp/controllers`、`src/harp/usecase`、`src/harp/core`、`src/harp/interface/ports`、`src/harp/adapters/driven` である。
- 関数優先の方針は `docs/design/harp_strategy_factory_design.md`、notebook の入口規約は `docs/operations/notebook_usage.md` を参照する。

## 1. レイヤ定義

| Layer | 主なパス | 責務 | 禁止事項 |
|---|---|---|---|
| Runtime composition root | `pipeline/runtime_settings.py` | `.env` / OS環境変数を読み、`HarpRuntimeConfig` を生成する | 業務判断、SQL、モデル計算 |
| Pipeline Jobs | `pipeline/jobs/*` | CLI引数解釈、runtime config生成、Controller呼び出し、最終出力 | Core / UseCase / Driven Adapter の直接呼び出し |
| Controller | `src/harp/controllers/*` | `*Command -> *Request` 変換、運用default・日付・パスの解決、UseCase呼び出し | SQL、学習・推論アルゴリズム、concrete adapter生成 |
| Domain-local composition root | `src/harp/controllers/*/deps.py` | runtime configから`*Deps`とconcrete Driven Adapterを組み立てる | 環境変数読込、業務判断、service locator化 |
| UseCase | `src/harp/usecase/*` | 解決済みRequestとPortを使った業務手順の順序制御 | SQL、YAML schema解釈、具象I/O、Driven Adapter直接依存 |
| Core | `src/harp/core/*` | 純粋計算、ドメイン判断、外部形式に依存しない意味モデル | DB / ファイル / MLflow I/O、wall clock参照、settings参照 |
| Ports | `src/harp/interface/ports/*` | UseCaseが必要とするDriven Adapter契約 | 実装詳細、副作用の実装 |
| Driven Adapter | `src/harp/adapters/driven/*` | DB、ファイル形式、MLflow、artifact保存など外部I/O | 業務意思決定、UseCaseの順序制御 |
| Shared | `src/harp/shared/*` | 明示引数で使う横断インフラとパス解決 | 環境変数由来のambient settings、UseCase固有ルール |

## 2. 依存方向

標準経路は次で固定する。

```text
pipeline/jobs
  -> load_pipeline_runtime_config()
  -> Controller(config).run(Command)
  -> controllers/<domain>/deps.py
  -> UseCase(Request, Deps)
  -> Core + Ports
  <- Driven Adapters
```

禁止事項:

1. `pipeline/jobs` は `harp.core`、`harp.usecase`、`harp.adapters.driven` を直接 import しない。
2. Controller本体は concrete Driven Adapter を importせず、生成は同domainの`deps.py`へ置く。
3. UseCaseはControllerやDriven Adapterをimportせず、CoreとPortを利用する。
4. Coreはouter layer、YAML、MLflow、wall clock、ambient settingsへ依存しない。
5. `src/harp` は環境変数や`.env`を読まず、完成したconfigまたは明示値を受け取る。

UseCase の差し替え可能性は `tests/flows/` で、外部依存を Port Mock に置換した Request / Result のブラックボックステストとして確認する。テスト方針の正本は `docs/design/testing_strategy.md` とする。

## 3. Runtime configとcomposition root

`src/harp/config.py` は値型だけを提供する。

- `DatabaseConfig`: 完成した`db_url`
- `MartConfig`: training / prediction mart table
- `TrackingConfig`: MLflow URIとexperiment名
- `PathConfig`: feature registry path
- `HarpRuntimeConfig`: 上記とlog levelの集約

`.env`とOS環境変数の解釈は`pipeline/runtime_settings.py`だけが担当する。`src/harp/shared/settings.py`と`get_settings()`は使用しない。DB adapter、`shared.db`、logging helperは必要値を明示引数で受け取る。

domain-local composition rootは以下に置く。

- `controllers/training/deps.py`
- `controllers/prediction/deps.py`
- `controllers/feature_validation/deps.py`
- `controllers/feature_selection/deps.py`
- `controllers/feature_contract/deps.py`
- `controllers/feature_registry/deps.py`
- `controllers/tracking/deps.py`
- `controllers/mlflow_store/deps.py`
- `controllers/table_export/deps.py`
- `controllers/notebook/deps.py`

共通DI containerやglobal service locatorは導入しない。複数domainでadapter生成の重複が実害になった場合にだけ再検討する。

## 4. 主なUseCase境界

| UseCase | Requestの状態 | 主責務 | 非責務 |
|---|---|---|---|
| `run_predict_place_usecase` | 日付、threshold、bankroll等が解決済み | feature / odds / race info取得、推論・EV Core呼び出し、結果集約 | 日付default、manifest JSON解釈、SQL |
| `run_train_pipeline_usecase` | task spec、feature set名、出力先が解決済み | 学習データ取得、Core学習、artifact / manifest / tracking保存指示 | recipe default解釈、YAML解釈、DB接続 |
| `run_feature_validation_usecase` | presetと出力パスが解決済み | scenario実行、判定Core呼び出し、成果物公開順序 | preset読込、feature YAML解釈、MLflow SDK |
| `run_feature_selection_usecase` | presetとbase feature set名が解決済み | scenario実行、選定Core呼び出し、materialization順序 | YAML schema解釈、具象runner、MLflow SDK |
| `run_export_feature_contract_usecase` | registry / target pathが解決済み | feature定義Port呼び出し、差分と書込順序 | YAML parse / dump |
| `run_log_condition_split_compare_usecase` | report / tracking設定が解決済み | report reader、pure payload builder、publisherの順序制御 | CSV parse、JSON生成、MLflow呼び出し |

`*Request` は業務上必須またはControllerで解決済みの値、`*Deps` はPort実装と実行設定、`*Result` は外側へ返す境界形式を保持する。

## 5. 外部形式とPort

| Port | 責務 | 主な実装 |
|---|---|---|
| `InferenceRepositoryPort` | 推論特徴量、オッズ、レース情報の取得 | `PostgresPolarsInferenceRepositoryAdapter` |
| `TrainingRepositoryPort` | 学習フレーム取得 | `PostgresTrainingRepositoryAdapter` |
| `FeatureDefinitionPort` | registry / contract / feature configの読込・render・検索 | `YamlFeatureDefinitionAdapter` |
| `ModelLoaderPort` | model artifact payload読込 | `PickleModelLoaderAdapter` |
| `ManifestReaderPort` | manifest JSONからmodel typeを取得 | `JsonManifestReaderAdapter` |
| `ManifestStorePort` | manifest生成・schema検証・JSON保存 | `JsonManifestStoreAdapter` |
| `ArtifactStorePort` | model artifact保存 | `PickleArtifactStoreAdapter` |
| `ConditionSplitReportReaderPort` | condition比較CSVを意味モデルへ変換 | `CsvConditionSplitReportReaderAdapter` |
| `ConditionTrackingPublisherPort` | tracking payloadをJSON / MLflowへ公開 | `TrackingConditionPublisherAdapter` |
| `TrackingPort` | run lifecycle、params、metrics、artifact記録 | `MlflowTrackingAdapter` |
| `MlflowStorePort` | file storeの検証・meta書換・移行 | `LocalMlflowStoreAdapter` |
| `TableParquetExportPort` | DB tableのParquet出力 | `PostgresCopyCsvParquetExportAdapter` |
| `FileGatewayPort` | 汎用text / bytes I/O | `LocalFileGatewayAdapter` |

外部形式の構文解釈はAdapter、形式に依存しないstatus解決やpayload意味モデルはCore、呼び出し順はUseCaseに置く。

## 6. 代表フロー

### 6.1 Prediction

1. Jobが`HarpRuntimeConfig`と`PredictPlaceCommand`を作る。
2. Controllerが`now`を注入して日付レンジを解決し、manifest候補の存在確認後にRequestを作る。
3. `prediction/deps.py`がrepository、model loader、manifest readerを構築する。
4. UseCaseがPortからデータを取得し、Coreで推論・補正・EV計算を行う。
5. Jobが結果を出力する。

### 6.2 Feature definition

1. Controllerがregistry / contract pathとfeature set名をRequestへ渡す。
2. UseCaseが`FeatureDefinitionPort`へ解決済みfeature setまたはrenderを要求する。
3. `YamlFeatureDefinitionAdapter`がYAMLを読み書きし、`core/feature_definitions.py`の純粋なschema意味解釈を利用する。
4. UseCaseはYAML documentを直接扱わない。

### 6.3 Condition tracking

1. `CsvConditionSplitReportReaderAdapter`がCSVを`ConditionSplitReport`へ変換する。
2. `core/condition_tracking.py`がparams / metrics / tags / summaryの意味モデルを作る。
3. `TrackingConditionPublisherAdapter`がJSONとtracking副作用を担当する。
4. UseCaseはこの3処理の順序だけを制御する。

## 7. Notebook境界

notebookもpackage側のambient settingsを使わない。repo内の標準notebookは`load_pipeline_runtime_config()`を入口で一度呼び、`NotebookFeatureConfigController(config)`または用途別Controllerへ渡す。

- feature registry / contract YAMLは`NotebookFeatureConfigController`経由で解決する。
- DB URLとmart tableはruntime configから受け取る。
- 繰り返す計算はCore、外部I/OはAdapterへ寄せ、notebookは探索・表示・実行パラメータに限定する。

詳細は`docs/operations/notebook_usage.md`を参照する。

## 8. 変更時チェックリスト

1. 処理を「業務手順 / 純粋計算 / 外部I/O / 実行入口」に分類したか。
2. operational default、`now`、環境変数解釈がControllerより内側へ入っていないか。
3. YAML / JSON / CSV / MLflowの具象処理がUseCaseやCoreへ入っていないか。
4. Controller本体がconcrete Driven Adapterを生成していないか。
5. DB URL、mart、tracking URIを明示注入しているか。
6. train / predict、pre-race / post-race、notebook / srcの境界を維持しているか。
7. `uv run pytest -q` で Flow / Calculation / Integration tests が通るか。

## 9. 参照

- `docs/design/harp_strategy_factory_design.md`
- `docs/design/testing_strategy.md`
- `docs/operations/notebook_usage.md`
- `AGENTS.md`
