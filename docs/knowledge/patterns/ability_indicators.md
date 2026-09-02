# 能力系指標の経験則

対象は、過去走の走破内容から作る能力 proxy（`pos4_agari_synergy`, `time_vs_avg` 系など）。

## 今の結論
- 能力系指標は、絶対値を増やすより先にレース内相対化を試す。
- 第一候補は `race内 z-score`。相対位置に加えて `race平均/分散` や `median` のような race集約量を足すと改善することがある。
- `robust = (x - median) / IQR` や `IQR` 単独は、現時点では z の置き換え先ではない。
- 分布が歪んだ指標（`time_diff` など）は、`z-score` より `rank` / `percentile` の方が効きやすいことがある。

## 使い方メモ
- 新しい能力 proxy を作ったら、まず `raw` と `race内 z-score` を比較する。
- `z` が残るなら、追加候補は `race平均/median` を優先し、次に `race分散/std/IQR` を試す。
- 分布が歪んでいるなら、`raw` / `z-score` / `rank` を並べて比較する。
- `top in race` 差分や `robust` 変換は、既存相対化との重複を疑ってから入れる。

## 経験則 1: 能力系指標はレース内相対化が効きやすい
- 見立て:
  - 能力系の絶対値は、出走メンバーの水準で意味が動きやすい。
  - 予測上ほしいのは「強いか」より「そのレースの中で相対的に優位か」であることが多い。
- 実務ルール:
  - 新規追加時の第一候補を `race内 z-score` にする。
  - `raw` を残す場合も、相対化 variant を同時に比較する。
- 根拠:
  - `20260306_pos4_agari_wavg5_relative_variants_feature_definition_validation_report.md`（runtime artifact）
    - `pos4_agari_synergy_wavg5_recent_z` を維持しつつ比較した結果、`z + median` は採用、`robust` と `iqr` は不採用。
  - `20260219_time_agari_drop_feature_definition.md`（runtime artifact）
    - `time_vs_avg_wavg5_recent_diff_top_in_race` は「同レース内差分」だが、既存の相対化系と重複寄与が強く OFF で改善。

## 経験則 2: z-score は強い基準線、robust は今のところ上位互換ではない
- 見立て:
  - 外れ値耐性を理由に `robust` を試す価値はあるが、少なくとも現状の能力系指標では z を上回る証拠が足りない。
- 実務ルール:
  - `robust` は z の代替として先に採用しない。
  - 比較するときは `z only` を baseline にして `z + robust` を見る。
- 根拠:
  - `20260306_pos4_agari_wavg5_relative_variants_feature_definition_validation_report.md`（runtime artifact）
    - `robust_only`, `z_plus_robust` ともに AUC / LogLoss で悪化し不採用。

## 経験則 3: race分布の中心値・散らばりは相対化を補完する候補になる
- 見立て:
  - z は「その馬の相対位置」は持つが、レース全体の能力水準までは持ちにくい。
  - `race平均` / `race median` は、レース全体が強いのか弱いのかを補助できる可能性がある。
  - `race分散` / `std` / `IQR` は、同レース内のバラつきの大きさを補助できる可能性がある。
- 実務ルール:
  - z を採用した能力指標では、次の一手として `race_<col>_avg` または `race_<col>_median` を試す。
  - その次に `race_<col>_var` / `race_<col>_std` / `race_<col>_iqr` のような spread 系を試す。
  - 現時点では、spread 系は center 系より優先度を下げる。
- 根拠:
  - 2026-03-06 の feature validation では、`race_pos4_agari_synergy_wavg5_recent_median` は `z` を維持したまま AUC / LogLoss を改善し採用、`race_pos4_agari_synergy_wavg5_recent_iqr` は不採用だった。
  - [feature_registry.yml](../../../pipeline/config/feature_registry.yml)
    - 現行 feature set でも `race_avg_*`, `race_stddev_*` 系は補助軸として採用されている。

## 経験則 4: 非正規分布の指標は z-score より rank の方が扱いやすいことがある
- 見立て:
  - `time_diff` のように裾が重い、外れ値が大きい、符号やスケールの歪みが強い指標では、平均との差より順位情報の方が安定しやすい。
  - モデル側も「どれだけ極端か」より「その race でどの順に良いか」を使った方が素直に学習しやすいことがある。
- 実務ルール:
  - 歪みが強い能力指標では `raw` / `z-score` / `rank` を同時に比較する。
  - 第一候補を 1 つに絞るなら、`time_diff` 系は `rank` から見る。
  - `rank` が効くときでも、絶対スケール情報が要るかは別で確認する。
- 根拠:
  - 保存済みの feature importance では、現行複勝モデルの `time_diff_wavg5_recent_rank` の gain が `time_diff_wavg5_recent_z` と `time_diff_wavg5_recent` を大きく上回った。
  - 現行単勝モデルでも `time_diff_wavg5_recent_rank` が同系統の `z` / `raw` より上に出た。
  - [feature_registry.yml](../../../pipeline/config/feature_registry.yml)
    - `time_diff_wavg5_recent_rank` と `same_cluster_avg_pos4_agari_synergy_rank` は現行 ON。

生成された CSV と日付付き validation report はリポジトリ外の runtime artifact として扱い、必要な場合は [feature validation の実行手順](../../operations/feature_validation_job_usage.md) から再生成する。

## 現時点の設計順
1. `raw`
2. 分布が素直なら `race内 z-score`
3. 分布が歪むなら `race内 rank`
4. `race平均 / median`
5. `race分散 / std / IQR`
6. 必要なら `top/min diff` や `robust`

## 開いたままの論点
- 能力系以外でも同じ順序が通用するか
- `rank` と `percentile` と `clipped z` のどれが最も安定するか
- 外れ値が極端なレース条件でのみ `robust` が効く局面があるか
