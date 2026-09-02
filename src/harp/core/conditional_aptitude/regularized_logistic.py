from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit


@dataclass(frozen=True)
class InteractionLogisticModel:
    entity_levels: tuple[str, ...]
    condition_levels: tuple[str, ...]
    entity_effects: np.ndarray
    condition_effects: np.ndarray
    interaction_effects: np.ndarray
    cell_counts: np.ndarray
    main_penalty: float
    interaction_penalty: float | None
    converged: bool
    iterations: int

    @property
    def has_interaction(self) -> bool:
        return self.interaction_penalty is not None

    def predict_proba(
        self,
        *,
        base_probability: np.ndarray,
        entity: pd.Series,
        condition: pd.Series,
    ) -> np.ndarray:
        base = _validate_base_probability(base_probability)
        if len(base) != len(entity) or len(base) != len(condition):
            raise ValueError("prediction arrays must have equal lengths")

        entity_lookup = {value: idx for idx, value in enumerate(self.entity_levels)}
        condition_lookup = {value: idx for idx, value in enumerate(self.condition_levels)}
        entity_values = normalize_category_series(
            entity,
            name="entity",
        ).to_numpy(dtype=str)
        condition_values = normalize_category_series(
            condition,
            name="condition",
        ).to_numpy(dtype=str)

        eta = _logit(base)
        for row_idx, (entity_value, condition_value) in enumerate(
            zip(entity_values, condition_values, strict=True)
        ):
            entity_idx = entity_lookup.get(entity_value)
            condition_idx = condition_lookup.get(condition_value)
            if entity_idx is not None:
                eta[row_idx] += self.entity_effects[entity_idx]
            if condition_idx is not None:
                eta[row_idx] += self.condition_effects[condition_idx]
            if self.has_interaction and entity_idx is not None and condition_idx is not None:
                eta[row_idx] += self.interaction_effects[entity_idx, condition_idx]
        return expit(eta).astype(float)

    def centered_interaction_effects(self) -> np.ndarray:
        if not self.has_interaction:
            return np.zeros_like(self.interaction_effects, dtype=float)
        # Fitted interactions already use a sum-to-zero contrast basis and
        # therefore cannot contain row- or column-constant main effects.
        return self.interaction_effects.copy()


def fit_regularized_interaction_logistic(
    frame: pd.DataFrame,
    *,
    outcome_col: str,
    base_probability_col: str,
    entity_col: str,
    condition_col: str,
    main_penalty: float,
    interaction_penalty: float | None,
    max_iter: int = 500,
    tolerance: float = 1e-8,
) -> InteractionLogisticModel:
    """Fit an offset logistic model with separately penalized effect blocks."""
    required = [outcome_col, base_probability_col, entity_col, condition_col]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise KeyError(f"regularized logistic columns are missing: {missing}")
    if frame.empty:
        raise ValueError("regularized logistic input must not be empty")
    if main_penalty <= 0.0:
        raise ValueError("main_penalty must be > 0")
    if interaction_penalty is not None and interaction_penalty <= 0.0:
        raise ValueError("interaction_penalty must be > 0 when enabled")

    y = _validate_binary_outcome(frame[outcome_col])
    base = _validate_base_probability(frame[base_probability_col].to_numpy(dtype=float))
    entity_idx, entity_levels = _encode_categories(frame[entity_col], name=entity_col)
    condition_idx, condition_levels = _encode_categories(frame[condition_col], name=condition_col)
    n_entities = len(entity_levels)
    n_conditions = len(condition_levels)
    cell_idx = entity_idx * n_conditions + condition_idx
    n_cells = n_entities * n_conditions
    cell_counts = np.bincount(cell_idx, minlength=n_cells).reshape(
        n_entities,
        n_conditions,
    )

    interaction_size = (
        (n_entities - 1) * (n_conditions - 1)
        if interaction_penalty is not None
        else 0
    )
    n_parameters = n_entities + n_conditions + interaction_size
    offset = _logit(base)

    def objective(parameters: np.ndarray) -> tuple[float, np.ndarray]:
        entity_effect = parameters[:n_entities]
        condition_effect = parameters[n_entities : n_entities + n_conditions]
        eta = offset + entity_effect[entity_idx] + condition_effect[condition_idx]

        if interaction_penalty is not None:
            interaction_contrasts = parameters[n_entities + n_conditions :]
            interaction_effect = _interaction_effects_from_contrasts(
                interaction_contrasts,
                n_entities=n_entities,
                n_conditions=n_conditions,
            )
            eta = eta + interaction_effect[entity_idx, condition_idx]
        else:
            interaction_effect = np.zeros(
                (n_entities, n_conditions),
                dtype=float,
            )

        probability = expit(eta)
        residual = probability - y
        loss = float(np.sum(np.logaddexp(0.0, eta) - y * eta))
        loss += 0.5 * float(main_penalty) * (
            float(np.dot(entity_effect, entity_effect))
            + float(np.dot(condition_effect, condition_effect))
        )

        gradient_entity = np.bincount(
            entity_idx,
            weights=residual,
            minlength=n_entities,
        ) + float(main_penalty) * entity_effect
        gradient_condition = np.bincount(
            condition_idx,
            weights=residual,
            minlength=n_conditions,
        ) + float(main_penalty) * condition_effect
        gradients = [gradient_entity, gradient_condition]

        if interaction_penalty is not None:
            loss += 0.5 * float(interaction_penalty) * float(
                np.sum(np.square(interaction_effect))
            )
            gradient_interaction = np.bincount(
                cell_idx,
                weights=residual,
                minlength=n_cells,
            ).reshape(n_entities, n_conditions)
            gradient_interaction += float(interaction_penalty) * interaction_effect
            gradients.append(
                _interaction_contrast_gradient(gradient_interaction)
            )
        return loss, np.concatenate(gradients)

    result = minimize(
        fun=objective,
        x0=np.zeros(n_parameters, dtype=float),
        method="L-BFGS-B",
        jac=True,
        options={"maxiter": int(max_iter), "ftol": float(tolerance)},
    )
    if not result.success:
        raise RuntimeError(
            "regularized logistic optimization failed to converge: "
            f"status={result.status}, message={result.message}"
        )
    if not np.isfinite(result.fun) or not np.all(np.isfinite(result.x)):
        raise RuntimeError("regularized logistic optimization produced non-finite values")

    parameters = np.asarray(result.x, dtype=float)
    entity_effects = parameters[:n_entities]
    condition_effects = parameters[n_entities : n_entities + n_conditions]
    if interaction_penalty is None:
        interaction_effects = np.zeros((n_entities, n_conditions), dtype=float)
    else:
        interaction_effects = _interaction_effects_from_contrasts(
            parameters[n_entities + n_conditions :],
            n_entities=n_entities,
            n_conditions=n_conditions,
        )

    return InteractionLogisticModel(
        entity_levels=entity_levels,
        condition_levels=condition_levels,
        entity_effects=entity_effects,
        condition_effects=condition_effects,
        interaction_effects=interaction_effects,
        cell_counts=cell_counts.astype(int),
        main_penalty=float(main_penalty),
        interaction_penalty=(
            None if interaction_penalty is None else float(interaction_penalty)
        ),
        converged=bool(result.success),
        iterations=int(result.nit),
    )


def weighted_double_center(
    effects: np.ndarray,
    weights: np.ndarray,
    *,
    iterations: int = 20,
) -> np.ndarray:
    """Remove exposure-weighted entity and condition means from cell effects."""
    values = np.asarray(effects, dtype=float).copy()
    weight_values = np.asarray(weights, dtype=float)
    if values.shape != weight_values.shape:
        raise ValueError("effects and weights must have the same shape")
    observed = weight_values > 0.0
    values[~observed] = 0.0

    for _ in range(int(iterations)):
        row_weight = weight_values.sum(axis=1)
        row_mean = np.divide(
            (values * weight_values).sum(axis=1),
            row_weight,
            out=np.zeros(values.shape[0], dtype=float),
            where=row_weight > 0.0,
        )
        values = values - row_mean[:, None]
        values[~observed] = 0.0

        column_weight = weight_values.sum(axis=0)
        column_mean = np.divide(
            (values * weight_values).sum(axis=0),
            column_weight,
            out=np.zeros(values.shape[1], dtype=float),
            where=column_weight > 0.0,
        )
        values = values - column_mean[None, :]
        values[~observed] = 0.0
    return values


def binary_log_loss(y_true: np.ndarray, probability: np.ndarray) -> float:
    y = np.asarray(y_true, dtype=float)
    p = np.clip(np.asarray(probability, dtype=float), 1e-12, 1.0 - 1e-12)
    if y.shape != p.shape:
        raise ValueError("binary log loss arrays must have equal shapes")
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log1p(-p)))


def binary_brier_score(y_true: np.ndarray, probability: np.ndarray) -> float:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(probability, dtype=float)
    if y.shape != p.shape:
        raise ValueError("binary Brier arrays must have equal shapes")
    return float(np.mean(np.square(p - y)))


def _encode_categories(series: pd.Series, *, name: str) -> tuple[np.ndarray, tuple[str, ...]]:
    values = normalize_category_series(series, name=name)
    levels = tuple(sorted(str(value) for value in values.unique().tolist()))
    lookup = {value: idx for idx, value in enumerate(levels)}
    indices = np.fromiter(
        (lookup[str(value)] for value in values),
        dtype=np.int64,
        count=len(values),
    )
    return indices, levels


def normalize_category_series(series: pd.Series, *, name: str) -> pd.Series:
    values = series.astype("string").str.strip()
    if values.isna().any() or (values == "").any():
        raise ValueError(f"category contains null or empty values: {name}")
    return values


def _interaction_effects_from_contrasts(
    contrasts: np.ndarray,
    *,
    n_entities: int,
    n_conditions: int,
) -> np.ndarray:
    """Expand free contrasts into a cell matrix with zero row and column sums."""
    effects = np.zeros((n_entities, n_conditions), dtype=float)
    if n_entities < 2 or n_conditions < 2:
        return effects
    free = np.asarray(contrasts, dtype=float).reshape(
        n_entities - 1,
        n_conditions - 1,
    )
    effects[:-1, :-1] = free
    effects[:-1, -1] = -free.sum(axis=1)
    effects[-1, :-1] = -free.sum(axis=0)
    effects[-1, -1] = float(free.sum())
    return effects


def _interaction_contrast_gradient(
    full_gradient: np.ndarray,
) -> np.ndarray:
    """Apply the transpose of the sum-to-zero contrast expansion."""
    if full_gradient.shape[0] < 2 or full_gradient.shape[1] < 2:
        return np.empty(0, dtype=float)
    contrast_gradient = (
        full_gradient[:-1, :-1]
        - full_gradient[:-1, -1][:, None]
        - full_gradient[-1, :-1][None, :]
        + full_gradient[-1, -1]
    )
    return contrast_gradient.ravel()


def _validate_binary_outcome(series: pd.Series) -> np.ndarray:
    values = pd.to_numeric(series, errors="coerce")
    if values.isna().any():
        raise ValueError("outcome contains invalid values")
    outcome = values.to_numpy(dtype=float)
    if not set(np.unique(outcome).tolist()).issubset({0, 1}):
        raise ValueError("outcome must contain only 0 and 1")
    return outcome


def _validate_base_probability(values: np.ndarray) -> np.ndarray:
    probability = np.asarray(values, dtype=float)
    if probability.ndim != 1:
        raise ValueError("base probability must be one-dimensional")
    if not np.all(np.isfinite(probability)):
        raise ValueError("base probability contains non-finite values")
    if np.any((probability <= 0.0) | (probability >= 1.0)):
        raise ValueError("base probability must be strictly between 0 and 1")
    return probability


def _logit(probability: np.ndarray) -> np.ndarray:
    return np.log(probability / (1.0 - probability))
