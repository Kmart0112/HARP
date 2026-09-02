---
name: dbt-execution
description: Run dbt commands in this repository with uv isolated execution (no local venv). Use this skill when asked to execute dbt after SQL/YAML model changes, perform full refresh rebuilds for changed content, or run the mart-wide build after broad project updates.
---

# Dbt Execution

## Overview

Run dbt only through `uv` in this repository. Select commands based on change scope and use named selectors so the default workflow does not rebuild heavy manual-refresh models such as `race_jodds`.

Primary execution mode (recommended, no local `.venv` creation):

```bash
uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1 dbt ...
```

Compatibility fallback (legacy `.venv-wsl`):

```bash
UV_PROJECT_ENVIRONMENT=.venv-wsl uv run --no-sync dbt ...
```

## First-Run Verification

1. Verify dbt toolchain:

```bash
uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1 dbt --version
```

2. Verify project/profile and DB connectivity:

```bash
uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1 dbt debug \
  --project-dir dbt/harp \
  --profiles-dir dbt/harp \
  --no-version-check
```

## Execution Rules

1. Run dbt build in isolated mode:

```bash
uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1 dbt build [options]
```

2. Rebuild with full refresh when content changed:

```bash
uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1 dbt build -f [options]
```

3. Run the default training / mart workflow with the named selector:

```bash
uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1 dbt build --selector training_default
```

When the next step is metrics notebook execution or formal feature validation, use the shell wrapper as the operational command:

```bash
scripts/refresh_analysis_cache.sh --full-refresh
```

4. Refresh the heavy manual `race_jodds` relation only when explicitly needed:

```bash
uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1 dbt build --selector manual_race_jodds_refresh
```

## Scope Decision

1. Use default scoped command for small/local model updates.
2. Use `-f` when data/content changes require recreation.
3. Use `--selector training_default` when changes affect the training / mart workflow.
4. Use `--selector manual_race_jodds_refresh` only when `race_jodds` itself must be rebuilt.

## Examples

```bash
# single target example
uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1 \
  dbt build -s features_jockey_style

# changed model/content example
uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1 \
  dbt build -f -s features_jockey_style

# default training / mart execution followed by parquet refresh
scripts/refresh_analysis_cache.sh --full-refresh

# if dbt was already run, refresh parquet only
scripts/refresh_analysis_cache.sh --skip-dbt

# heavy race_jodds refresh only when explicitly needed
uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1 \
  dbt build --selector manual_race_jodds_refresh
```

## Legacy `.venv-wsl` Fallback

Use this only when isolated execution is blocked by local constraints.

```bash
UV_PROJECT_ENVIRONMENT=.venv-wsl uv run --no-sync dbt build --selector training_default
```
