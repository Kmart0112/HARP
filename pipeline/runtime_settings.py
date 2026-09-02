from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

from harp.config import (
    DatabaseConfig,
    HarpRuntimeConfig,
    MartConfig,
    PathConfig,
    TrackingConfig,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class TableExportRuntimeConfig:
    db_url: str
    source_table: str


@dataclass(frozen=True)
class PredictRuntimeDefaults:
    bankroll: float
    kelly_fraction: float
    kelly_cap: float


def load_pipeline_env_files(env_file: str | Path | None = None) -> None:
    """Load pipeline env files without overriding real OS env vars."""

    if env_file is not None:
        resolved_env_file = Path(env_file)
        if resolved_env_file.exists():
            load_dotenv(resolved_env_file, override=False)
        return

    env_name = _resolve_env_name(DEFAULT_ENV_FILE)
    candidates: list[Path] = []
    if env_name:
        candidates.append(PROJECT_ROOT / f".env.{env_name}")
    candidates.append(DEFAULT_ENV_FILE)

    for candidate in candidates:
        if candidate.exists():
            load_dotenv(candidate, override=False)


def load_pipeline_runtime_config(env_file: str | Path | None = None) -> HarpRuntimeConfig:
    load_pipeline_env_files(env_file=env_file)

    return HarpRuntimeConfig(
        database=DatabaseConfig(db_url=_required_env("HARP_DB_URL")),
        mart=MartConfig(
            training_mart_table=_required_env("HARP_TRAINING_MART_TABLE"),
            prediction_mart_table=_required_env("HARP_PREDICTION_MART_TABLE"),
        ),
        tracking=TrackingConfig(
            mlflow_tracking_uri=_required_env("HARP_MLFLOW_TRACKING_URI"),
            train_experiment=_required_env("HARP_MLFLOW_TRAIN_EXPERIMENT"),
            feature_validation_experiment=_required_env("HARP_MLFLOW_FEATURE_VALIDATION_EXPERIMENT"),
            feature_selection_experiment=_required_env("HARP_MLFLOW_FEATURE_SELECTION_EXPERIMENT"),
        ),
        paths=PathConfig(feature_sets_path=_required_env("HARP_FEATURE_SETS_PATH")),
        log_level=_required_env("HARP_LOG_LEVEL").upper(),
    )


def load_table_export_runtime_config(env_file: str | Path | None = None) -> TableExportRuntimeConfig:
    load_pipeline_env_files(env_file=env_file)
    return TableExportRuntimeConfig(
        db_url=_required_env("HARP_DB_URL"),
        source_table=_required_env("HARP_TRAINING_MART_TABLE"),
    )


def load_predict_runtime_defaults(env_file: str | Path | None = None) -> PredictRuntimeDefaults:
    load_pipeline_env_files(env_file=env_file)
    bankroll = _optional_float("HARP_PREDICT_FUKUSHO_BANKROLL", default=223000.0)
    kelly_fraction = _optional_float("HARP_PREDICT_FUKUSHO_KELLY_FRACTION", default=0.1)
    kelly_cap = _optional_float("HARP_PREDICT_FUKUSHO_KELLY_CAP", default=0.05)
    if kelly_fraction < 0.0:
        raise ValueError("HARP_PREDICT_FUKUSHO_KELLY_FRACTION must be >= 0.0")
    if not 0.0 <= kelly_cap <= 1.0:
        raise ValueError("HARP_PREDICT_FUKUSHO_KELLY_CAP must be between 0.0 and 1.0")
    return PredictRuntimeDefaults(
        bankroll=bankroll,
        kelly_fraction=kelly_fraction,
        kelly_cap=kelly_cap,
    )


def _resolve_env_name(default_env_file: Path) -> str | None:
    env_name = os.getenv("HARP_ENV") or os.getenv("APP_ENV")
    if env_name is not None and env_name.strip():
        return env_name.strip()

    if not default_env_file.exists():
        return None

    values = dotenv_values(default_env_file)
    file_env_name = values.get("HARP_ENV") or values.get("APP_ENV")
    if file_env_name is None or not str(file_env_name).strip():
        return None
    return str(file_env_name).strip()


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ValueError(f"Missing required pipeline setting: {name}")
    return value.strip()


def _optional_float(name: str, *, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid float pipeline setting: {name}={raw!r}") from exc
