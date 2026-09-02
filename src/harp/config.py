from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DatabaseConfig:
    db_url: str


@dataclass(frozen=True)
class MartConfig:
    training_mart_table: str
    prediction_mart_table: str


@dataclass(frozen=True)
class TrackingConfig:
    mlflow_tracking_uri: str
    train_experiment: str
    feature_validation_experiment: str
    feature_selection_experiment: str


@dataclass(frozen=True)
class PathConfig:
    feature_sets_path: str


@dataclass(frozen=True)
class HarpRuntimeConfig:
    database: DatabaseConfig
    mart: MartConfig
    tracking: TrackingConfig
    paths: PathConfig
    log_level: str
