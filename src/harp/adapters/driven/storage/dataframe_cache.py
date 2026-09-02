from __future__ import annotations

from pathlib import Path

import pandas as pd


_PARQUET_ENGINE = "pyarrow"


def _to_path(path: str | Path) -> Path:
    return path if isinstance(path, Path) else Path(path)


def resolve_dataframe_cache_path(cache_path: str | Path) -> Path:
    parquet_path = _to_path(cache_path)
    if parquet_path.exists():
        return parquet_path

    raise FileNotFoundError(f"DataFrame cache not found: parquet={parquet_path}")


def dataframe_cache_exists(cache_path: str | Path) -> bool:
    try:
        resolve_dataframe_cache_path(cache_path)
    except FileNotFoundError:
        return False
    return True


def load_dataframe_cache(cache_path: str | Path) -> pd.DataFrame:
    resolved_path = resolve_dataframe_cache_path(cache_path)
    return pd.read_parquet(resolved_path, engine=_PARQUET_ENGINE)


def save_dataframe_cache(df: pd.DataFrame, cache_path: str | Path) -> Path:
    parquet_path = _to_path(cache_path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(
        parquet_path,
        engine=_PARQUET_ENGINE,
        index=False,
    )
    return parquet_path
