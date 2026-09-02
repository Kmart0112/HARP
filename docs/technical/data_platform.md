# Data Platform

## PostgreSQL

HARP の分析用データは PostgreSQL を前提にしている。ローカルの起動手順は [../operations/local_environment.md](../operations/local_environment.md) を参照する。

接続設定は `.env.example` を起点にし、`HARP_DB_HOST`、`HARP_DB_PORT`、`HARP_DB_USER`、`HARP_DB_PASSWORD`、`HARP_DB_NAME` または `HARP_DB_URL` で指定する。

## dbt

dbt プロジェクトは `dbt/harp` に置く。モデルは staging、intermediate、core、features、mart、sokuho、lab に分ける。

通常の学習・mart 更新は、重いモデルを避ける selector を使う。

```bash
uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1 \
  dbt build --project-dir dbt/harp --profiles-dir dbt/harp --no-version-check \
  --selector training_default
```

詳細は [../../dbt/harp/README.md](../../dbt/harp/README.md) を参照する。
モデルや列の documentation の書き方は [dbt_documentation_guidelines.md](dbt_documentation_guidelines.md) を参照する。

## Docker

ローカル PostgreSQL と Superset は `docker/docker-compose.yml` に定義されている。普段の開発では `postgres` service だけ起動すればよい。

Superset は可視化確認用の補助ツールとして扱う。正式な分析結果や採否判断の保存先は MLflow、notebook/report、docs/knowledge に寄せる。
