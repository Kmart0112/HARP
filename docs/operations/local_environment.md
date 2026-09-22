# ローカル環境構築

## 目的

README には概要だけを置き、PostgreSQL や Docker の具体的な手順はこのファイルで管理する。

## 環境変数

`.env.example` を `.env` にコピーして、接続先やパスワードを環境に合わせて変更する。

```bash
cp .env.example .env
```

環境を `local`、`dev`、`prod` のように切り替える場合は、`.env.dev` / `.env.prod` を作り、`HARP_ENV=dev` のように指定する。OS 環境変数が最優先で、`.env` は既存の環境変数を上書きしない。

dbt は `scripts/dbt` 経由で実行すると `.env` を自動で読む。
シェルで `HARP_ENV=dev` を指定すれば `.env.dev` が `.env` より優先される。
SSH 先などのリモート PostgreSQL を使う場合も、`.env` の `HARP_DB_HOST`、
`HARP_DB_PORT`、`HARP_DB_USER`、`HARP_DB_PASSWORD`、`HARP_DB_NAME` を設定する。
Python pipeline 用の `HARP_DB_URL` も同じDBを指すように設定する。

```bash
scripts/dbt debug --project-dir dbt/harp --profiles-dir dbt/harp --no-version-check
```

実値を含む `.env` / `.env.<env>` は Git 管理外とし、設定例には実値を書かない。

direnv を使う場合:

```bash
cp .envrc.example .envrc
direnv allow
```

PowerShell の例:

```powershell
Copy-Item .env.example .env
notepad .env
```

## PostgreSQL 起動

HARP 用 PostgreSQL は `docker/docker-compose.yml` の `postgres` service を使う。

```bash
docker compose -f docker/docker-compose.yml up -d postgres
docker compose -f docker/docker-compose.yml ps
```

接続確認:

```bash
docker exec -it harp-postgres psql -U postgres -d horse_db
```

## 停止

```bash
docker compose -f docker/docker-compose.yml down
```

volume も消す場合:

```bash
docker compose -f docker/docker-compose.yml down -v
```

## Superset

Superset も同じ compose file に含まれる。必要な場合だけ全 service を起動する。

```bash
docker compose -f docker/docker-compose.yml up -d
```

通常の学習・検証では Superset は必須ではない。


## オッズ契約v1の接続と再実行

通常の学習・推論は `.env.example` の `HARP_TRAINING_MART_TABLE`、`HARP_PREDICTION_MART_TABLE`、各 `*_QUOTES_TABLE` を使用する。`HARP_DB_URL` が空なら、dbtと共通の `HARP_DB_HOST/PORT/USER/PASSWORD/NAME` からURLを安全に組み立てる。明示したURLがある場合はそちらを優先する。

当日入力、10分前オッズの構築、入力保存と再実行は [odds_input_contract.md](../design/odds_input_contract.md) の手順を使う。新規モデルの公開先は従来と同じで、既存artifactへ契約を後付けして互換扱いにしない。
