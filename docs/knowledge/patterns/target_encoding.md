# ターゲットエンコーディングの経験則

対象は、`sire` / `jockey` / `trainer` などの主体について、過去成績や能力 proxy を entity 単位・条件単位で集約する特徴量。

## 今の結論
- TE は `overall -> 粗い条件付き -> 細かい条件付き` の順で試す。最初から条件を切りすぎない。
- 同じ entity でも勝ちやすい target は違う。`sire` は `place_rate` と `avg_pos4` の併用が有力で、`jockey` は `place_rate` 系が安定しやすい。
- 条件付き TE は「追加」より「置換」で勝つことがある。既存 TE と重なる軸は add-on だけで判断しない。
- `smooth` は全体複勝率への shrink をかける形が安定しやすく、`diff` / `diff_logit` のような全体差分系も相性がよい。
- `sire × age` や `馬体重` のように、そもそも複勝率がぶれやすい条件軸は効きにくく、今後も要検証。

## 使い方メモ
- 新しい TE は、まず `overall` の `place_rate_smooth` を基準に置く。
- 次に同じ条件粒度で `place_rate` / `avg_pos4_agari_synergy` / 必要なら `time_diff` を比べる。
- その後で `cluster`、`surface`、`distance_bucket`、`jyo_cd` のような粗い条件付き TE を 1 本ずつ足す。
- `smooth` を作るときは、まず全体複勝率へ寄せる設計を第一候補にする。
- 既存の強い TE と軸が重なるなら、`add-on比較` と `置換比較` を分けて行う。
- 条件軸自体の複勝率が不安定そうなら、採用候補ではなく探索候補として扱う。
- 採用は最小列数を優先し、少差なら列数が少ない側を残す。

## 経験則 1: overall TE を先に固める
- 見立て:
  - 条件付き TE は魅力的でも、まず entity 自体の基礎能力や基礎成績を押さえた overall TE が土台になる。
  - 条件付き TE を先に増やすと、疎化と重複で評価が不安定になりやすい。
- 実務ルール:
  - 第一候補は `overall place_rate_smooth`。
  - 追加候補として `overall avg_pos4_agari_synergy` を比べる。
  - `time_diff` 系は改善しても、列数増に見合うかを別で判断する。
- 根拠:
  - `20260302_sire_overall_te_with_readd_exploration_feature_definition_validation_report.md`（runtime artifact）
    - `sire_avg_place_rate_smooth` と `sire_avg_pos4_agari_synergy` は単体で改善し、2列併用が最良。
    - `sire_avg_time_diff` も改善したが、正式採用は外している。

## 経験則 2: entity ごとに勝ちやすい target が違う
- 見立て:
  - `place_rate` は結果に近い安定集約、`avg_pos4` は能力 proxy、`time_diff` はスケールや分布の癖が強い。
  - どの主体にどの target が合うかは一律ではない。
- 実務ルール:
  - `sire` では `place_rate` だけでなく `avg_pos4` も必ず比較する。
  - `jockey` では、まず `place_rate` 系を主系列として置く。
  - entity ごとに勝者を決めてから条件付きへ進む。
- 根拠:
  - `20260302_sire_overall_te_with_readd_exploration_feature_definition_validation_report.md`（runtime artifact）
    - `sire_avg_pos4_agari_synergy` は `sire_avg_place_rate_smooth` と同等以上に有効で、併用も効く。
  - `20260302_jockey_conditional_pos4_vs_place_feature_definition_validation_report.md`（runtime artifact）
    - `jockey` は `overall` / `cluster` ともに `place_rate` が `avg_pos4` を上回る。

## 経験則 3: 条件付き TE は coarse な軸から始める
- 見立て:
  - 条件適性は存在しても、距離ジャストや多重条件のような細粒度はサンプル不足と冗長性の影響を受けやすい。
  - `cluster`、`surface`、`distance_bucket`、`jyo_cd` くらいの粗さが最初の比較単位になりやすい。
- 実務ルール:
  - 追加順は `cluster / surface / distance_bucket / jyo_cd / age` を優先する。
  - `surface × exact distance` のような細粒度は後回しにする。
  - 条件数を増やすほど、単列比較で勝てないものは早めに切る。
- 根拠:
  - `target_encoding_report_20260217.md`（runtime artifact）
    - `same_surface_sire_avg_diff_logit`、`same_dist_bucket_sire_avg_place_rate_smooth` は単列で改善。
    - `jockey_surface_condition_*` は改善が小さいか悪化方向。
  - `20260303_jockey_surface_conditional_te_feature_definition_validation_report.md`（runtime artifact）
    - `surface×distance exact`、`surface×distance±200m`、`surface×jyo_cd`、`surface×style` は、既存騎手 base への add-on としては全滅。

## 経験則 4: add-on だけでなく置換比較をする
- 見立て:
  - 既存の TE と同じ役割の列は、追加すると冗長で負けやすい。
  - ただし別候補へ丸ごと置き換えると勝つことがある。
- 実務ルール:
  - `base + candidate` 比較に加えて、`current_only vs candidate_only` を必ず行う。
  - 特に `cluster` と `jyo` のように近い意味の条件軸は置換比較を優先する。
- 根拠:
  - `20260303_jockey_surface_conditional_te_feature_definition_validation_report.md`（runtime artifact）
    - `jockey_surface_jyo_place_rate_3y_smooth` は add-on では不採用。
  - `20260303_jockey_cluster_vs_distance_jyo_feature_definition_validation_report.md`（runtime artifact）
    - `jyo_only` は `cluster_only` より AUC / LogLoss で優位。
    - 一方で距離条件は置換しても劣後。

## 経験則 5: `smooth` は全体複勝率への shrink を第一候補にする
- 見立て:
  - TE の素の平均値は母数差の影響を受けやすい。
  - 全体複勝率へ寄せる `smooth` は、少サンプル主体や条件セルでも壊れにくい。
  - `diff`、`diff_logit` は「その主体が全体平均からどれだけズレるか」を持てるので、`smooth` と相性がよい。
- 実務ルール:
  - 同じ条件なら、まず「全体複勝率へ shrink した `*_smooth`」を見る。
  - 次に `*_diff` や `*_diff_logit` を比較する。
  - 素の平均だけでなく「全体差分」を候補に入れる。
- 根拠:
  - `target_encoding_report_20260217.md`（runtime artifact）
    - `same_surface_sire_avg_diff_logit` は単列比較で安定改善。
    - `same_dist_bucket_sire_avg_place_rate_smooth` も改善方向。

## 経験則 6: 複勝率がぶれやすい条件軸は効きにくい
- 見立て:
  - `sire × age` や `馬体重` のような軸は、母数の薄さや分布の偏りで複勝率自体が安定しにくい。
  - その場合、`smooth` をかけても signal より noise が残りやすい。
- 実務ルール:
  - 条件軸自体の複勝率が安定していないなら、正式採用ではなく探索扱いから入る。
  - `age` や `weight` は、より粗い bucket 化や別 target（`avg_pos4` など）も含めて再検証する。
  - `same_weight_*` のような未検証軸は、まず単列比較から始める。
- 根拠:
  - `20260302_sire_conditional_pos4_vs_place_feature_definition_validation_report.md`（runtime artifact）
    - `same_age_sire_avg_place_rate_smooth_prev_age` は単体で非優位、`same_age_sire_avg_pos4_agari_synergy` は不採用。
  - `20260302_sire_overall_te_with_readd_exploration_feature_definition_validation_report.md`（runtime artifact）
    - `same_age_sire_avg_place_rate_smooth_prev_age` は参考再投入では改善したが、正式判断では強い勝ち筋として固定されていない。
  - [feature_registry.yml](../../../pipeline/config/feature_registry.yml)
    - `same_weight_sire_place_rate` は現時点で OFF のまま。

## 経験則 7: 条件適性の存在と、特徴量としての採用は分けて考える
- 見立て:
  - 「主体×条件で差がある」ことと、「その TE を今の特徴量集合に足すと改善する」ことは別問題。
  - 条件適性は事前仮説のスクリーニングには使えるが、採用判定は最終的に予測指標で行う。
- 実務ルール:
  - GLMM や集計検定で条件適性を確認しても、そのまま採用しない。
  - 最後は LightGBM の add-on / replace 比較で決める。
- 根拠:
  - `20260304_glmm_jockey_sire_condition_aptitude_validation_report_pos4_z.md`（runtime artifact）
    - `jockey` / `sire` ともに `distance_bucket`、`jyo_cd`、`course_cluster` でグローバル適性あり。
  - `20260303_jockey_surface_conditional_te_feature_definition_validation_report.md`（runtime artifact）
    - それでも既存 base への追加では採用列が出ていない。

## 推奨検証順
1. `overall place_rate_smooth` を baseline にする
2. 同一粒度で `place_rate` / `avg_pos4` / `time_diff` を単体比較する
3. 勝ち筋の target で coarse 条件付き TE を 1 列ずつ add-on 比較する
4. `smooth` は全体複勝率への shrink を先に試す
5. 既存 TE と役割が近い列は `current_only vs candidate_only` の置換比較をする
6. 採用候補が複数あるときは family 単位で同時比較する
7. 最終的に最小列数のセットへ圧縮する

日付付き validation report はリポジトリ外の runtime artifact として扱い、必要な場合は [feature validation の実行手順](../../operations/feature_validation_job_usage.md) から再生成する。

## 現時点の設計順
1. `overall place_rate_smooth`
2. `overall avg_pos4_agari_synergy`
3. `cluster` / `surface` / `distance_bucket` / `jyo_cd` の coarse conditional TE
4. 全体複勝率への shrink を使った `*_smooth`
5. `diff` / `diff_logit`
6. `age` / `weight` のような不安定軸は探索枠で別管理
7. 細粒度の交差条件や多列同時追加

## 開いたままの論点
- `trainer` 系 TE の正式な勝ち筋はまだ弱く、`surface` 以外の条件軸比較が必要
- `sire` 条件付き TE は `place` 系と `pos4` 系の最終セットが時系列で揺れており、再固定が必要
- `sire × weight` 系はまだ未検証に近く、bucket 設計から見直しが必要
- `jockey_surface_jyo_place_rate_3y_smooth` は置換候補として有望なので、正式切替の再評価余地がある
