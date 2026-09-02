# HARP テスト戦略

## 1. 目的

HARP のテストは、実装レイヤーや内部関数を固定するためではなく、正式な処理が公開境界の契約どおり動くことを確認する。

基本単位は次とする。

```text
Request
  -> UseCase
  -> Result + 外部へ公開された成果物
```

UseCase の外部依存は `src/harp/interface/ports` の Port Mock へ差し替える。テストは UseCase の内部関数、呼び出し順、具象 Adapter を知らない状態を維持する。

## 2. テスト分類

### 2.1 Flow tests

配置先は `tests/flows/` とする。

- 公開 Request を入力する
- `*Deps` には `create_autospec(..., spec_set=True)` で作った Port Mock を渡す
- Core の純粋計算は Mock 化せず実際に動かす
- Result、生成された report / CSV / YAML / artifact、外部状態を確認する
- private helper や内部関数を monkeypatch しない

状態を持つ `TrackingPort` や `FileGatewayPort` は、Port Mock にインメモリ状態を持つ side effect を設定する。完全な `mock_calls` の順序ではなく、処理後に外部へ残った意味のある状態を確認する。

### 2.2 Calculation tests

配置先は `tests/calculations/` とする。

EV、Kelly、確率補正、採否判断など、業務上重要な純粋計算だけを入力と期待出力で確認する。内部 helper の網羅を目的にしない。

### 2.3 Integration tests

配置先は `tests/integrations/` とする。

FileGateway、Parquet、MLflow など、実 Adapter の Port 契約を最小限の round-trip で確認する。UseCase の業務判断はここで再テストしない。

## 3. 対象外

次のテストは原則として追加しない。

- CLI、runtime config、Controller のデフォルト値固定
- Job が Controller を呼んだ、Controller が UseCase を呼んだ、という配線確認
- `deps.py` が特定の具象クラスを生成したことの確認
- private helper の呼び出し回数や完全な呼び出し順
- docs の存在や文言だけを固定するテスト
- proposal、TODO、未実装機能を先取りしたテスト
- 実装レイヤーのディレクトリ構造をそのまま複製した重複テスト

不具合の回帰テストも、可能な限り最寄りの公開 Request から再現する。

## 4. 現在の正式フロー

現在は次を Flow test の対象とする。

- Prediction
- Training
- Feature Validation
- Feature Selection
- Feature Contract export
- Feature Registry render
- Table Parquet export
- MLflow store migration
- Condition tracking
- Notebook artifact export
- Artifact explanation dataset rebuild

正式入口が存在しない機能にはテストを追加しない。新しい正式フローを追加した場合は、実装完了後に同じ Request / Port Mock / Result 形式で追加する。

## 5. 実行

全体:

```bash
uv run pytest -q
```

分類別:

```bash
uv run pytest -q tests/flows
uv run pytest -q tests/calculations
uv run pytest -q tests/integrations
```
