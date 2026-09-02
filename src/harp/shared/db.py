from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

@lru_cache(maxsize=4)
def _engine_for_url(db_url: str) -> Engine:
    return create_engine(
        db_url,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def get_engine(db_url: str) -> Engine:
    if not db_url.strip():
        raise ValueError("db_url is required.")
    return _engine_for_url(db_url)


def read_sql_df(
    sql: str,
    *,
    db_url: str,
    params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    engine = get_engine(db_url)
    return pd.read_sql_query(text(sql), con=engine, params=params)


def test_connection(db_url: str) -> bool:
    engine = get_engine(db_url)
    with engine.connect() as conn:
        value = conn.execute(text("SELECT 1")).scalar_one()
    return value == 1
