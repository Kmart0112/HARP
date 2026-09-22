# HARP dbt 実行ガイド

このプロジェクトでは dbt を `uv tool run --isolated` 経由で実行する。

`scripts/dbt` はリポジトリ直下の `.env` を自動で読む。
`HARP_ENV=dev` のように環境を指定した場合は `.env.dev` も読み、
優先順位は OS 環境変数 > `.env.<HARP_ENV>` > `.env` とする。
`APP_ENV` は `HARP_ENV` 未指定時の別名として使える。
接続情報は Git 管理外の env ファイルに置く。

```bash
scripts/dbt debug --project-dir dbt/harp --profiles-dir dbt/harp --no-version-check
```

## 標準ワークフロー

通常の学習 / mart 更新では、重い `fct_jodds_snapshot` を再計算しない named selector を使う。
`training_default` は新学習martと、packageが使用中の互換出力を更新する。

```bash
scripts/dbt build --project-dir dbt/harp --profiles-dir dbt/harp --no-version-check \
  --selector training_default
```

## `fct_jodds_snapshot` 手動更新

`fct_jodds_snapshot` は重いため、必要な時だけ専用 selector で更新する。

```bash
scripts/dbt build --project-dir dbt/harp --profiles-dir dbt/harp --no-version-check \
  --selector manual_fct_jodds_snapshot_refresh
```

## 依存ルール

- 通常系モデルは canonical な `fct_*` / `feat_*` / `m_train_*` を内部参照する。
- 通常系モデルは `published_manual.fct_jodds_snapshot` を参照し、`fct_jodds_snapshot` モデル自体は通常 DAG に含めない。
- `fct_jodds_snapshot` は手動更新済みの `core.fct_jodds_snapshot` を前提に downstream が参照する。

## dbt MCP

プロジェクト内の MCP 設定は以下で管理する。

- Codex: `.codex/config.toml`
- VS Code: `.vscode/mcp.json`
- Claude Code など `mcpServers` 形式のクライアント: `.mcp.json`

dbt MCP は CLI tools 専用のローカル MCP として `uvx dbt-mcp` で起動し、dbt CLI は `scripts/dbt` ラッパー経由で実行する。ラッパーはこのプロジェクトの標準に合わせて `uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1` を使う。

DB 接続先は `dbt/harp/profiles.yml` と `HARP_DB_*` / `DBT_TARGET` の環境変数で決める。MCP も `scripts/dbt` 経由なら env ファイルを自動で読む。`uv tool run` を直接使う場合は、`--env-file .env` を追加するか direnv などで環境変数を読み込む。
