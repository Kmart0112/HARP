from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import lightgbm as lgb

from .dataset_builder import BinaryDataset
from .task_types import TaskKind

PLACE_MODEL_PARAMS: dict[str, Any] = {
    "objective": "binary",
    "n_estimators": 4000,
    "learning_rate": 0.03,
    "num_leaves": 15,
    "max_depth": 4,
    "subsample": 0.8,
    "colsample_bytree": 0.6,
    "min_child_samples": 400,
    "min_split_gain": 0.01,
    "reg_alpha": 0.0,
    "reg_lambda": 0.0,
    "random_state": 42,
    "verbosity": -1,
    "n_jobs": -1,
}

WIN_MODEL_PARAMS: dict[str, Any] = {
    "objective": "binary",
    "n_estimators": 12000,
    "learning_rate": 0.015,
    "num_leaves": 31,
    "max_depth": 5,
    "subsample": 0.7,
    "colsample_bytree": 0.7,
    "min_child_samples": 80,
    "min_split_gain": 0.1,
    "reg_alpha": 0.5,
    "reg_lambda": 1.0,
    "random_state": 42,
    "verbosity": -1,
    "n_jobs": -1,
}


@dataclass(frozen=True)
class TrainingRecipe:
    task_kind: TaskKind
    model_params: dict[str, Any]
    fit_kwargs: dict[str, Any] | None


def build_place_recipe(ds: BinaryDataset) -> TrainingRecipe:
    fit_kwargs: dict[str, Any] = {
        "eval_metric": "binary_logloss",
        "callbacks": [
            lgb.early_stopping(stopping_rounds=200),
            lgb.log_evaluation(period=50),
        ],
        "eval_set": [(ds.X_val, ds.y_val)],
    }
    return TrainingRecipe(
        task_kind=TaskKind.PLACE,
        model_params=dict(PLACE_MODEL_PARAMS),
        fit_kwargs=fit_kwargs,
    )


def build_win_recipe() -> TrainingRecipe:
    return TrainingRecipe(
        task_kind=TaskKind.WIN,
        model_params=dict(WIN_MODEL_PARAMS),
        fit_kwargs=None,
    )


TrainingRecipeBuilder = Callable[[BinaryDataset], TrainingRecipe]


def _build_win_recipe_from_dataset(_ds: BinaryDataset) -> TrainingRecipe:
    return build_win_recipe()


RECIPE_BUILDERS: dict[TaskKind, TrainingRecipeBuilder] = {
    TaskKind.PLACE: build_place_recipe,
    TaskKind.WIN: _build_win_recipe_from_dataset,
}


def build_training_recipe(*, task_kind: TaskKind | str, ds: BinaryDataset) -> TrainingRecipe:
    try:
        resolved_task_kind = task_kind if isinstance(task_kind, TaskKind) else TaskKind.from_str(str(task_kind))
        recipe_builder = RECIPE_BUILDERS[resolved_task_kind]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Unknown task_kind for training recipe: {task_kind!r}") from exc
    return recipe_builder(ds)
