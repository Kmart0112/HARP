# HARP 関数優先アーキテクチャ補足

## 0. 位置づけ
本書は、HARP の現行コードで採用する「関数優先」の設計補足である。
責務境界の正本は `docs/design/hexagonal_responsibility_split.md` を優先する。

## 1. 基本方針
HARP では、疎結合と依存注入は外部 I/O 境界を守るために使う。
学習、推論、補正、EV 計算などの純粋計算は、原則として `src/harp/core` の関数として実装する。

クラスや Strategy は、状態を持つ必要がある、複数実装を同じ実行時契約で差し替える必要がある、または既存の外部ライブラリ API を包む必要がある場合だけ導入する。

## 2. 現行で採用している形

### 2.1 Hexagonal の最小境界
- `pipeline/jobs` は CLI 入口として引数を解釈する。
- `controllers` は `Command -> Request` 変換と Port 実装の注入を行う。
- `usecase` は処理手順を関数で組み立てる。
- `core` は DataFrame や配列を受け取る純粋計算を担当する。
- `adapters/driven` は DB、ファイル、artifact、MLflow などの外部 I/O を担当する。

### 2.2 Port / DI を残す対象
Port は次のような外部 I/O 境界に限定する。

- DB 読み込み
- ファイル読み書き
- artifact / manifest 保存
- model payload 読み込み
- MLflow tracking
- notebook や外部コマンド実行

UseCase は Port 経由でこれらを呼び、Driven Adapter 実装を直接 import しない。

### 2.3 関数でよい対象
次の処理は、特別な理由がなければ Strategy クラスにしない。

- LightGBM 学習
- Platt 補正
- logit shift
- データセット分割
- EV 計算
- 出力列整形

これらは `src/harp/core` の関数として実装し、UseCase から直接呼ぶ。

## 3. Train / Predict の現行マッピング
- Train UseCase: `src/harp/usecase/training/usecase.py`
- Predict UseCase: `src/harp/usecase/prediction/place.py`
- LightGBM 学習: `src/harp/core/training/binary_trainer.py`
- Platt 補正: `src/harp/core/training/algorithms/calibration/platt_logodds.py`
- logit shift: `src/harp/core/training/algorithms/calibration/logit_shift.py`
- Controller 依存注入: `src/harp/controllers/training/deps.py`

## 4. 境界ルール
1. UseCase は Driven Adapter 実装を直接 import しない。
2. SQL 文字列は `adapters/driven/db` に限定する。
3. Core に外部 I/O を持ち込まない。
4. `pipeline/jobs` は入力解釈と Controller 呼び出しに限定する。
5. 単なる委譲クラスや将来拡張用の Strategy は作らない。

## 5. 更新ルール
1. 依存方向やレイヤ責務を変える場合は、先に `docs/design/hexagonal_responsibility_split.md` を更新する。
2. 純計算の実装方針だけを変える場合は、本書を更新する。
3. 将来案は現行ルールと混ぜず、必要なら `notes/` に置く。
