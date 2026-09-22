from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DatabaseConfig:
    db_url: str


@dataclass(frozen=True)
class MartConfig:
    training_mart_table: str
    prediction_mart_table: str
    training_quotes_table: str = "intermediate.int_odds_pre10m_v1"
    prediction_quotes_table: str = "staging.stg_s_odds_quotes_v1"


@dataclass(frozen=True)
class TrackingConfig:
    mlflow_tracking_uri: str
    train_experiment: str
    feature_validation_experiment: str
    feature_selection_experiment: str


@dataclass(frozen=True)
class PathConfig:
    feature_sets_path: str
    prediction_snapshots_path: str = "pipeline/artifacts/prediction_inputs"


@dataclass(frozen=True)
class HarpRuntimeConfig:
    database: DatabaseConfig
    mart: MartConfig
    tracking: TrackingConfig
    paths: PathConfig
    log_level: str
