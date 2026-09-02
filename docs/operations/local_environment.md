# ローカル環境構築

## 目的

README には概要だけを置き、PostgreSQL や Docker の具体的な手順はこのファイルで管理する。

## 環境変数

`.env.example` を `.env` にコピーして、接続先やパスワードを環境に合わせて変更する。

```bash
cp .env.example .env
```

環境を `local`、`dev`、`prod` のように切り替える場合は、`.env.dev` / `.env.prod` を作り、`HARP_ENV=dev` のように指定する。OS 環境変数が最優先で、`.env` は既存の環境変数を上書きしない。

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
