# HARP dbt 実行ガイド

このプロジェクトでは dbt を `uv tool run --isolated` 経由で実行する。

## 標準ワークフロー

通常の学習 / mart 更新では、重い `fct_jodds_snapshot` を再計算しない named selector を使う。

```bash
uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1 \
  dbt build --project-dir dbt/harp --profiles-dir dbt/harp --no-version-check \
  --selector training_default
```

## `fct_jodds_snapshot` 手動更新

`fct_jodds_snapshot` は重いため、必要な時だけ専用 selector で更新する。

```bash
uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1 \
  dbt build --project-dir dbt/harp --profiles-dir dbt/harp --no-version-check \
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

DB 接続先は `dbt/harp/profiles.yml` と `HARP_DB_*` / `DBT_TARGET` の環境変数で決める。必要に応じて `.env` / `.env.local` を direnv などで読み込んでから MCP クライアントを起動する。
