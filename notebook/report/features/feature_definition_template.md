# 特徴量定義テンプレート（実行単位）

1回の実行につき1ファイルを作る。複数特徴量はこの1ファイルにまとめる。

## 0. 実行情報
- 実行日: YYYY-MM-DD
- 担当:
- 実行名: （何を変えた実行か）
- 関連レポート: `notebook/report/features/YYYYMMDD_<change_summary>_feature_definition_validation_report.md`

## 1. 変更一覧（複数特徴量をここで管理）
| 特徴量名 | 種別 | 変更種別 | 作り方/意味の1行要約 | 判定 |
|---|---|---|---|---|
| feature_a | num/cat/cluster | add/update/drop | 例: 過去5走平均を標準化し近走安定度を表す | 採用/保留/不採用 |
| feature_b | num/cat/cluster | add/update/drop |  |  |

## 2. 特徴量詳細（必要なものだけ）
### 2.1 `<feature_name>`
- 作り方: （利用テーブル・主な式・集計窓を簡潔に）
- 意味: （何を表すか、なぜ効く想定か）
- リークチェック: as-of / 同一レース結果の不使用を確認
- 実装反映先: （dbtモデル、`mart.m_train_race_horse_past5`列、`features.py`）

必要な数だけ `2.x` を追加する。

## 3. 実行メモ（任意）
- 重複候補との関係:
- 注意点:
