# NN用の出走履歴と共通事前特徴

NNは馬ごとの過去走系列と今回の出走馬集合を受け取る。DBでは1出走1行を維持し、
履歴の取得・padding・mask・テンソル化はPython側の責務とする。
dbt入力に加え、Pythonの入力契約・Repository・入力保存は実装済み。
[Python入力Portの契約](nn_input_repository_contract.md)を参照する。
レース単位Dataset、前処理、NumPy配列・padding・mask、作成Jobは実装済み。
[Dataset作成の契約・実行手順](nn_dataset_preparation.md)を参照する。NN本体と学習は未実装。

## モデルと既存経路

| モデル | 粒度 | 役割 |
|---|---|---|
| `feat_race_entry_pre_race` | `race_id, kettonum` | context、調教、主体・コースの事前統計を結合する共通層 |
| `m_race_entry_feature_matrix` | `race_id, kettonum` | 共通層へ既存の過去走集計・相対特徴を追加するLightGBM出口 |
| `int_race_entry_run_record` | `race_id, kettonum` | 当時の事前特徴とその走の結果を持つ、番号付きの馬別履歴 |
| `m_nn_race_entry` | `race_id, kettonum` | 今回の事前特徴と履歴参照終端。教師・オッズを持たない |

`m_race_inputs_v1` / `m_training_inputs_v1` と既存の教師・オッズ契約は維持する。
共通層は既存matrixの結合・式を移したもので、統計窓、平滑化、NULL、既存matrixの列名・型・列順を変更しない。
統計の集計元へ新しい統計付き履歴表を戻して循環を作らない。

## 出走番号と参照終端

`run_no` は、馬ごとに `held_date, race_id` の昇順で1から振る。収録データ内の実出走番号であり、
地方・海外など未収録の出走も含めた生涯出走回数を意味しない。永続キーは `race_id, kettonum`。

履歴には結果factにある出走と、既知の競走中止・失格・再騎乗・降着を残す。
JV-Data異常区分2101の1/2/3（取消・発走除外・競走除外）は除外し、4/5/6/7は実出走として扱う。
結果factにない異常走の計測値は `stg_n_uma_race_all` から取得する。欠測を0で補完しない。
[JRA-VAN JV-Data仕様書](https://jra-van.jp/dlb/sdv/sdk/JV-Data4901.pdf)

`history_end_no` は対象開催日より厳密に前の最後の `run_no`。履歴なしは0。
対象レース自体、同日・未来のレースは参照しない。直近K走は次の条件で取れる。

```text
同じkettonum AND history_end_no - K < run_no <= history_end_no
```

新馬、短い履歴、欠損統計、欠損オッズを理由に今回の馬を削除しない。
今回の集合では非出走を除き、競走中止等の実出走馬も残す。教師ラベルが未取得なら
学習側で不完全レースとして扱い、結果から今回の入力集合を縮めない。

過去走の追加・削除・日付訂正では連番が変わり得る。履歴表は全保存期間からtableとして再構築し、
その後に対象出走表も再構築する。同じ版の履歴と参照終端を必ず利用する。
Python側で学習するときはこれらの入力と特徴順序を固定したartifactとして保存する必要がある。

## 主体ID・統計・時点

`macros/nn_input_columns.sql` の `nn_pre_race_feature_columns()` が、履歴と今回に共通の入力列順を定義する。
騎手・厩舎・生産者・血統のIDや名前・識別用カテゴリはNN出口に出さず、既存の平滑化複勝率と母数を使う。
競馬場・馬場など条件を表すカテゴリは含む。`race_id` / `kettonum` / 日付 / 参照終端は管理列で、
全数値列を自動で学習特徴にすることは禁止する。欠損フラグの利用も入力設定で明示する。

過去走にはその過去走の月・年に対応する統計を付け、今回の値で過去走を再評価しない。
`monthly_stats_cutoff` は対象月初、`yearly_stats_cutoff` は対象年初で、当該月・年は集計から除かれる。
母数0と統計行がない状態は同一視しない。`*_stats_missing` は率の未取得を表し、必ずしも経験ゼロではない。

次は既存挙動として保持しており、この変更での改善対象ではない。

- 騎手等の月次窓は暦期間ではなく観測月の行数。騎手は前35行、血統は既存設定に従う。
- 厩舎・生産者は年次更新。発走直前までの最新集計ではない。
- 平滑化の固定prior、未観測月のlookup不足、調教等の入力欠損。

この契約は日付・集計期間による境界を保証する。情報の発表・受信時刻を使った厳密なpoint-in-time再構築ではない。
共通context自体が最新状態を反映し得るので、予測時点の完全再現には既存の保存入力機構をNN履歴へ拡張する必要がある。
統計列だけでなく、結果fact・context・調教の収録範囲と鮮度はupstreamの責務である。

## 更新と検証

既存contextと統計lookupが構築済みなら、期間指定なしで初回の共通層・全履歴を作る。

```bash
scripts/dbt build --project-dir dbt/harp --profiles-dir dbt/harp \
  --selector nn_inputs --full-refresh --vars '{"feature_input_mode":"training"}'
```

upstreamから作る場合は `nn_training` を使う。LightGBMの通常 `training_default` も共通層を親として構築する。
selectorでは別経路との比較テストを切り分け、NNだけの更新で未更新のLightGBM matrixとの一致を要求しない。
既存のLightGBM selectorもNN martの事前構築を要求しない。
共通層のfull refreshに対象日・期間を指定すると古い履歴を失うため、コンパイルエラーとして拒否する。
対象範囲の更新はincrementalで行い、履歴表は保存済みの全期間から番号を再構築する。

```bash
scripts/dbt build --project-dir dbt/harp --profiles-dir dbt/harp \
  --selector nn_inputs --vars '{"race_from_date":"2026-06-01","race_to_date":"2026-06-14"}'
```

当日の特徴だけ更新する場合は、履歴表の構築・結果更新を済ませてから `nn_current` を使う。
このselectorは当日context、共通層、今回のNN出走表だけを更新する。context用spine・declaredと統計lookupは事前に必要。

```bash
scripts/dbt build --project-dir dbt/harp --profiles-dir dbt/harp \
  --selector nn_current --vars '{"feature_input_mode":"latest","target_held_date":"2026-06-13"}'
```

履歴表は対象日フィルタを適用しない。履歴保持済みの共通層に対して今回の出走表だけを期間指定しても、
その期間以前の過去走を参照できる。

主キー、連番、参照終端の前後、全頭保持、入力列境界、共通値の一致をdata testで検証する。
unit testでは、順不同で追加された履歴、取消、競走中止、未確定出馬、新馬、欠損統計、同日・未来の履歴を検証する。
