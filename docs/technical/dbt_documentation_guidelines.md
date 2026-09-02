# dbt Documentation Guidelines

## 目的

HARP の dbt documentation は、人間とエージェントが同じ前提でモデルを参照できるようにするためのカタログである。

dbt の YAML は、モデルや列を見た瞬間に「何のためのデータか」「どの粒度か」「どの時点で使えるか」を判断するために使う。
設計判断や背景説明は `docs/` に置き、YAML には参照時に必要な最小限の意味と制約を残す。

## 参照先の分担

| 場所 | 役割 |
|---|---|
| `dbt/harp/models/**/*.yml` | dbt catalog とエージェントの即時参照。モデル、列、テスト、最小限の運用上の注意を書く。 |
| `dbt/harp/models/**/*_docs.md` または `_common_docs.md` | `{{ doc("...") }}` で再利用する共通語彙や長めの説明を書く。 |
| `docs/design/` | DAG、責務境界、リーク防止、学習/推論分離などの設計判断を書く。 |
| `docs/analysis/` | 分析データ作成や modeling workflow の使い方を書く。 |
| `dbt/harp/README.md` | dbt の実行方法、selector、MCP などの運用入口を書く。 |

YAML に設計書の内容を丸ごと移さない。
逆に、モデルの粒度や重要列の意味を `docs/` だけに閉じ込めず、dbt catalog から直接読めるようにする。

## モデル説明の標準

モデルごとに、原則として次を説明する。

- 役割: 何を表すモデルか。
- 粒度: 主キー、または一意になる列の組み合わせ。
- 利用用途: training、inference、reporting、feature lookup など。
- 時点境界: pre-race、race-day、post-race のどれに属するか。
- リーク境界: レース後にしか分からない情報を含むか、推論時に使ってよいか。
- 重要な upstream/downstream: 読み手が迷いやすい場合だけ書く。

短いモデルでは 1-3 文でよい。
複雑なモデルでは `description: "{{ doc('model_xxx') }}"` とし、docs block に表や箇条書きを置く。

```yaml
version: 2

models:
  - name: m_race_entry_feature_matrix
    description: "{{ doc('model_m_race_entry_feature_matrix') }}"
    config:
      meta:
        harp:
          layer: mart
          grain: ["race_id", "kettonum", "feature_snapshot_type"]
          role: common_feature_matrix
          availability: pre_race
          leakage_boundary: result_free
```

## カラム説明の標準

カラム説明は、SQL を読まなくても用途を判断できる粒度にする。

- ID 列: 何の識別子か、raw の由来が重要なら由来を書く。
- 日付/年月列: as-of 境界、rolling cutoff、対象期間を明記する。
- 指標列: 分母、分子、窓、平滑化、null 条件を書く。
- ラベル列: レース後ラベルであり推論特徴量に使わないことを書く。
- snapshot 列: `pre10m`、`final`、`latest` などの意味を書く。
- flag 列: true になる条件を書く。

式をそのまま長く写さない。
詳細な式は SQL、意味と利用上の注意は YAML、背景判断は `docs/` に分ける。

```yaml
columns:
  - name: race_id
    description: "{{ doc('col_race_id') }}"
    tests:
      - not_null

  - name: feature_snapshot_type
    description: "{{ doc('col_feature_snapshot_type') }}"
    tests:
      - not_null

  - name: is_place
    description: "{{ doc('col_is_place') }}"
```

## 共通 docs block

複数モデルに出る列や語彙は docs block に寄せる。

優先して共通化する語彙:

- `race_id`
- `kettonum`
- `held_date`
- `horse_number`
- `feature_snapshot_type`
- `is_win`
- `is_place`
- `result_order`
- `odds_tansho`
- `popularity`
- `entry_status`
- `is_prediction_target`

docs block 名は、列なら `col_<column_name>`、モデルなら `model_<model_name>` を基本にする。

```markdown
{% docs col_feature_snapshot_type %}

Feature snapshot timing.
Training rows use `pre10m` or `final`.
Race-day inference rows use `latest`.

{% enddocs %}
```

## 言語と文体

説明文は基本的に日本語で書く。
SQL 識別子、dbt 用語、タグ、指標名、feature 名は英語のままにする。

既存の英語説明は無理に一括翻訳しない。
新規または大きく触るモデルから、日本語主体にそろえる。

## meta の使い方

空の `config: meta: {}, tags: []` は新規に増やさない。

エージェントや人間が検索・判定に使う値だけ、`config.meta.harp` に置く。

推奨キー:

- `layer`: `staging`、`intermediate`、`core`、`features`、`mart`、`sokuho`、`lab`
- `grain`: 一意性を期待する列の配列
- `role`: `source_shape`、`canonical_fact`、`feature_lookup`、`common_feature_matrix`、`training_output`、`inference_output` など
- `availability`: `pre_race`、`race_day`、`post_race`、`mixed`
- `leakage_boundary`: `result_free`、`post_race_label`、`evaluation_only` など

`meta` は補助情報であり、実行 selector の正本にはしない。
selector に使う実行単位は SQL の `config(tags=[...])` と `dbt/harp/selectors.yml` を正本にする。

## テストの扱い

HARP の既存 YAML では `tests:` が使われている。
dbt 1.10 系では `data_tests:` も使えるが、キー名の移行は documentation 統一とは別作業にする。

当面は既存に合わせて `tests:` を使い、次の列に優先して付ける。

- モデルの grain を構成する列
- join key
- snapshot type
- ラベル列の not null が期待される training output
- enum 的に値域が決まる列

## 優先順位

全モデルを一括で埋めるより、参照頻度と誤用リスクが高いモデルから整える。

1. `mart/training`、`mart/inference` の出口モデル
2. `m_race_entry_feature_matrix` とその入力 context
3. 主要な `features/*`
4. `core/fact/*`
5. `staging/*`
6. `sources.yml`
7. `lab/*`

`sources.yml` や raw 由来の staging は列数が多いため、全列説明を無理に埋めるより、下流で使われる列と誤解しやすい列を優先する。

## 作業チェック

dbt documentation を追加・変更するときは、次を確認する。

1. モデルの役割、粒度、用途、時点境界が YAML から読めるか。
2. train/predict、pre-race/post-race の境界が曖昧になっていないか。
3. 共通列の説明を重複して手書きせず、docs block に寄せられるか。
4. 空 description や空 meta を増やしていないか。
5. 変更した YAML が dbt の parse 対象として壊れていないか。

最小検証:

```bash
uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1 \
  dbt parse --project-dir dbt/harp --profiles-dir dbt/harp --no-version-check
```

docs サイトまで確認する場合:

```bash
uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1 \
  dbt docs generate --project-dir dbt/harp --profiles-dir dbt/harp --no-version-check
```
