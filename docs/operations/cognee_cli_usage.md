# Cognee CLI Usage

`cognee` は、HARP ではまず知識検索専用の CLI として使う。
初期対象は `docs/knowledge` で、学習・推論パイプラインにはまだ接続しない。

## 目的
- `docs/knowledge` を agent が横断検索できるようにする
- 調査時の第一手を repo 全文検索ではなく、知識グラフ検索に寄せる
- hexagonal 構成の本体コードにはまだ依存を広げない

## 前提
- 依存は `uv` で管理し、`cognee` は `knowledge` extra として導入する
- `LLM_API_KEY` は `.env.local` に設定する
- Cognee の保存先は repo 配下の `outputs/cognee` を使う

ラッパースクリプトは `uv run --extra knowledge` を使うため、通常は事前インストール不要。
環境を先に同期する場合は `uv sync --extra knowledge` を実行する。

## 設定値
非 secret の既定値は `.env` に置く。

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
VECTOR_DB_PROVIDER=lancedb
GRAPH_DATABASE_PROVIDER=kuzu
HARP_COGNEE_SYSTEM_ROOT=outputs/cognee/system
HARP_COGNEE_DATA_ROOT=outputs/cognee/data
ENABLE_BACKEND_ACCESS_CONTROL=false
```

secret は gitignore 対象の `.env.local` に置く。

```dotenv
LLM_API_KEY=
```

## 初回構築
知識 docs を追加して knowledge graph を再構築する。

```bash
bash scripts/cognee-rebuild-knowledge.sh
```

別ディレクトリや別データセット名を使いたい場合:

```bash
bash scripts/cognee-rebuild-knowledge.sh docs/knowledge harp_knowledge
```

## 検索
既定では `harp_knowledge` に対して `GRAPH_COMPLETION` で検索する。

```bash
bash scripts/cognee-search.sh "target encoding の採用条件は?"
```

根拠断片を優先したい場合:

```bash
COGNEE_QUERY_TYPE=CHUNKS bash scripts/cognee-search.sh "target encoding の採用条件は?"
```

## 生 CLI
ラッパーを通して任意の `cognee-cli` サブコマンドを実行できる。

```bash
bash scripts/cognee.sh --help
bash scripts/cognee.sh search --datasets harp_knowledge "query"
```

## 運用ルール
- agent の調査はまず `bash scripts/cognee-search.sh` を試す
- 根拠確認が必要なときは `COGNEE_QUERY_TYPE=CHUNKS` を使う
- `docs/knowledge` 更新後は再度 `bash scripts/cognee-rebuild-knowledge.sh` を実行する
- 重要判断は Cognee の結果だけで確定せず、元ファイルも確認する
