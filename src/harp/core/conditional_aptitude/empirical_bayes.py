from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar
from scipy.special import expit
from scipy.stats import norm

from .regularized_logistic import (
    InteractionLogisticModel,
    fit_regularized_interaction_logistic,
    normalize_category_series,
    weighted_double_center,
)


@dataclass(frozen=True)
class EmpiricalBayesInteractionModel:
    main_model: InteractionLogisticModel
    interaction_modes: np.ndarray
    interaction_sds: np.ndarray
    centered_interaction_modes: np.ndarray
    tau_logodds: float

    def predict_proba(
        self,
        *,
        base_probability: np.ndarray,
        entity: pd.Series,
        condition: pd.Series,
    ) -> np.ndarray:
        main_probability = self.main_model.predict_proba(
            base_probability=base_probability,
            entity=entity,
            condition=condition,
        )
        eta = _logit(main_probability)
        entity_lookup = {
            value: idx for idx, value in enumerate(self.main_model.entity_levels)
        }
        condition_lookup = {
            value: idx for idx, value in enumerate(self.main_model.condition_levels)
        }
        for row_idx, (entity_value, condition_value) in enumerate(
            zip(
                normalize_category_series(entity, name="entity").to_numpy(
                    dtype=str
                ),
                normalize_category_series(condition, name="condition").to_numpy(
                    dtype=str
                ),
                strict=True,
            )
        ):
            entity_idx = entity_lookup.get(entity_value)
            condition_idx = condition_lookup.get(condition_value)
            if entity_idx is not None and condition_idx is not None:
                eta[row_idx] += self.interaction_modes[entity_idx, condition_idx]
        return expit(eta).astype(float)


@dataclass(frozen=True)
class EmpiricalBayesFitResult:
    model: EmpiricalBayesInteractionModel
    cell_effects: pd.DataFrame
    eligible_coverage: float
    interaction_rms_probability: float
    reliable_cell_count: int
    reliable_exposure_share: float


def fit_empirical_bayes_interactions(
    frame: pd.DataFrame,
    *,
    outcome_col: str,
    base_probability_col: str,
    entity_col: str,
    condition_col: str,
    entity_label_col: str | None,
    main_penalty: float,
    min_entity_total_n: int,
    min_condition_levels: int,
    min_cell_n_for_claim: int,
    practical_delta_probability: float,
    local_probability_threshold: float,
    confidence_level: float = 0.95,
) -> EmpiricalBayesFitResult:
    if frame.empty:
        raise ValueError("empirical Bayes input must not be empty")
    if entity_label_col is not None and entity_label_col not in frame.columns:
        raise KeyError(f"entity label column is missing: {entity_label_col}")

    main_model = fit_regularized_interaction_logistic(
        frame,
        outcome_col=outcome_col,
        base_probability_col=base_probability_col,
        entity_col=entity_col,
        condition_col=condition_col,
        main_penalty=main_penalty,
        interaction_penalty=None,
    )
    base_probability = frame[base_probability_col].to_numpy(dtype=float)
    main_probability = main_model.predict_proba(
        base_probability=base_probability,
        entity=frame[entity_col],
        condition=frame[condition_col],
    )
    y = pd.to_numeric(frame[outcome_col], errors="raise").to_numpy(dtype=float)
    entity_lookup = {value: idx for idx, value in enumerate(main_model.entity_levels)}
    condition_lookup = {
        value: idx for idx, value in enumerate(main_model.condition_levels)
    }
    entity_idx = np.fromiter(
        (
            entity_lookup[str(value)]
            for value in normalize_category_series(
                frame[entity_col],
                name=entity_col,
            )
        ),
        dtype=np.int64,
        count=len(frame),
    )
    condition_idx = np.fromiter(
        (
            condition_lookup[str(value)]
            for value in normalize_category_series(
                frame[condition_col],
                name=condition_col,
            )
        ),
        dtype=np.int64,
        count=len(frame),
    )
    n_entities = len(main_model.entity_levels)
    n_conditions = len(main_model.condition_levels)
    cell_idx = entity_idx * n_conditions + condition_idx
    n_cells = n_entities * n_conditions
    cell_counts_flat = np.bincount(cell_idx, minlength=n_cells).astype(int)
    observed_mask = cell_counts_flat > 0
    offset = _logit(main_probability)

    tau = _estimate_tau_laplace(
        y=y,
        offset=offset,
        cell_idx=cell_idx,
        n_cells=n_cells,
        observed_mask=observed_mask,
    )
    modes_flat, information_flat = _fit_cell_modes(
        y=y,
        offset=offset,
        cell_idx=cell_idx,
        n_cells=n_cells,
        tau=tau,
    )
    posterior_sd_flat = np.sqrt(1.0 / information_flat)
    modes = modes_flat.reshape(n_entities, n_conditions)
    posterior_sds = posterior_sd_flat.reshape(n_entities, n_conditions)
    cell_counts = cell_counts_flat.reshape(n_entities, n_conditions)
    centered_modes = weighted_double_center(modes, cell_counts)

    cell_effects = _build_cell_effects(
        frame=frame,
        entity_col=entity_col,
        condition_col=condition_col,
        entity_label_col=entity_label_col,
        outcome_col=outcome_col,
        main_probability=main_probability,
        entity_levels=main_model.entity_levels,
        condition_levels=main_model.condition_levels,
        entity_idx=entity_idx,
        condition_idx=condition_idx,
        cell_counts=cell_counts,
        modes=modes,
        centered_modes=centered_modes,
        posterior_sds=posterior_sds,
        min_entity_total_n=min_entity_total_n,
        min_condition_levels=min_condition_levels,
        min_cell_n_for_claim=min_cell_n_for_claim,
        practical_delta_probability=practical_delta_probability,
        local_probability_threshold=local_probability_threshold,
        confidence_level=confidence_level,
    )
    observed_effects = cell_effects.loc[cell_effects["cell_n"] > 0].copy()
    eligible_rows = observed_effects.loc[observed_effects["eligible"]]
    total_n = int(observed_effects["cell_n"].sum())
    eligible_n = int(eligible_rows["cell_n"].sum())
    eligible_coverage = float(eligible_n / total_n) if total_n else 0.0

    if eligible_rows.empty:
        interaction_rms_probability = 0.0
        reliable_exposure_share = 0.0
    else:
        weights = eligible_rows["cell_n"].to_numpy(dtype=float)
        effects = eligible_rows["effect_probability"].to_numpy(dtype=float)
        interaction_rms_probability = float(
            np.sqrt(np.average(np.square(effects), weights=weights))
        )
        reliable_n = int(
            eligible_rows.loc[eligible_rows["reliable"], "cell_n"].sum()
        )
        reliable_exposure_share = float(reliable_n / eligible_n) if eligible_n else 0.0

    model = EmpiricalBayesInteractionModel(
        main_model=main_model,
        interaction_modes=modes,
        interaction_sds=posterior_sds,
        centered_interaction_modes=centered_modes,
        tau_logodds=float(tau),
    )
    return EmpiricalBayesFitResult(
        model=model,
        cell_effects=cell_effects,
        eligible_coverage=eligible_coverage,
        interaction_rms_probability=interaction_rms_probability,
        reliable_cell_count=int(cell_effects["reliable"].sum()),
        reliable_exposure_share=reliable_exposure_share,
    )


def _estimate_tau_laplace(
    *,
    y: np.ndarray,
    offset: np.ndarray,
    cell_idx: np.ndarray,
    n_cells: int,
    observed_mask: np.ndarray,
) -> float:
    observed_count = int(observed_mask.sum())
    if observed_count == 0:
        return 1e-4

    def negative_log_marginal(log_tau: float) -> float:
        tau = float(np.exp(log_tau))
        modes, information = _fit_cell_modes(
            y=y,
            offset=offset,
            cell_idx=cell_idx,
            n_cells=n_cells,
            tau=tau,
        )
        eta = offset + modes[cell_idx]
        log_likelihood = -float(np.sum(np.logaddexp(0.0, eta) - y * eta))
        observed_modes = modes[observed_mask]
        observed_information = information[observed_mask]
        log_marginal = log_likelihood
        log_marginal -= 0.5 * float(np.dot(observed_modes, observed_modes)) / (tau * tau)
        log_marginal -= observed_count * np.log(tau)
        log_marginal -= 0.5 * float(np.sum(np.log(observed_information)))
        return -float(log_marginal)

    result = minimize_scalar(
        negative_log_marginal,
        bounds=(np.log(1e-4), np.log(2.0)),
        method="bounded",
        options={"xatol": 1e-3},
    )
    if not result.success or not np.isfinite(result.fun):
        raise RuntimeError("failed to estimate empirical Bayes interaction scale")
    return float(np.exp(result.x))


def _fit_cell_modes(
    *,
    y: np.ndarray,
    offset: np.ndarray,
    cell_idx: np.ndarray,
    n_cells: int,
    tau: float,
) -> tuple[np.ndarray, np.ndarray]:
    prior_precision = 1.0 / (float(tau) * float(tau))

    def objective(modes: np.ndarray) -> tuple[float, np.ndarray]:
        eta = offset + modes[cell_idx]
        probability = expit(eta)
        residual = probability - y
        loss = float(np.sum(np.logaddexp(0.0, eta) - y * eta))
        loss += 0.5 * prior_precision * float(np.dot(modes, modes))
        gradient = np.bincount(
            cell_idx,
            weights=residual,
            minlength=n_cells,
        ) + prior_precision * modes
        return loss, gradient

    result = minimize(
        objective,
        x0=np.zeros(n_cells, dtype=float),
        method="L-BFGS-B",
        jac=True,
        options={"maxiter": 300, "ftol": 1e-9},
    )
    if not result.success:
        raise RuntimeError(
            "empirical Bayes cell optimization failed to converge: "
            f"status={result.status}, message={result.message}"
        )
    if not np.isfinite(result.fun) or not np.all(np.isfinite(result.x)):
        raise RuntimeError("empirical Bayes cell optimization produced non-finite values")
    modes = np.asarray(result.x, dtype=float)
    probability = expit(offset + modes[cell_idx])
    likelihood_information = np.bincount(
        cell_idx,
        weights=probability * (1.0 - probability),
        minlength=n_cells,
    )
    return modes, likelihood_information + prior_precision


def _build_cell_effects(
    *,
    frame: pd.DataFrame,
    entity_col: str,
    condition_col: str,
    entity_label_col: str | None,
    outcome_col: str,
    main_probability: np.ndarray,
    entity_levels: tuple[str, ...],
    condition_levels: tuple[str, ...],
    entity_idx: np.ndarray,
    condition_idx: np.ndarray,
    cell_counts: np.ndarray,
    modes: np.ndarray,
    centered_modes: np.ndarray,
    posterior_sds: np.ndarray,
    min_entity_total_n: int,
    min_condition_levels: int,
    min_cell_n_for_claim: int,
    practical_delta_probability: float,
    local_probability_threshold: float,
    confidence_level: float,
) -> pd.DataFrame:
    alpha = 1.0 - float(confidence_level)
    z_value = float(norm.ppf(1.0 - alpha / 2.0))
    entity_labels = _resolve_entity_labels(
        frame,
        entity_col=entity_col,
        entity_label_col=entity_label_col,
    )
    outcome = pd.to_numeric(frame[outcome_col], errors="raise").to_numpy(dtype=float)
    entity_total = cell_counts.sum(axis=1)
    condition_levels_per_entity = (cell_counts > 0).sum(axis=1)
    rows: list[dict[str, object]] = []

    for entity_position, entity_id in enumerate(entity_levels):
        for condition_position, condition_id in enumerate(condition_levels):
            mask = (entity_idx == entity_position) & (condition_idx == condition_position)
            cell_n = int(cell_counts[entity_position, condition_position])
            if cell_n:
                reference_probability = float(np.mean(main_probability[mask]))
                successes = int(np.sum(outcome[mask]))
                expected_successes = float(np.sum(main_probability[mask]))
            else:
                reference_probability = float(np.mean(main_probability))
                successes = 0
                expected_successes = 0.0

            model_effect = float(modes[entity_position, condition_position])
            centered_effect = float(
                centered_modes[entity_position, condition_position]
            )
            # The diagonal Laplace variance belongs to the raw cell mode.  Keep
            # interval and reliability calculations on that same scale; the
            # centered value is descriptive only unless its full covariance is
            # propagated through the centering transform.
            effect = model_effect
            effect_sd = float(posterior_sds[entity_position, condition_position])
            effect_low = effect - z_value * effect_sd
            effect_high = effect + z_value * effect_sd
            effect_probability = _probability_shift(reference_probability, effect)
            effect_probability_low = _probability_shift(reference_probability, effect_low)
            effect_probability_high = _probability_shift(reference_probability, effect_high)
            probability_practical = _probability_outside_practical_range(
                mean=effect,
                sd=effect_sd,
                reference_probability=reference_probability,
                practical_delta_probability=practical_delta_probability,
            )
            eligible = bool(
                cell_n >= min_cell_n_for_claim
                and entity_total[entity_position] >= min_entity_total_n
                and condition_levels_per_entity[entity_position] >= min_condition_levels
            )
            reliable = bool(
                eligible and probability_practical >= local_probability_threshold
            )
            rows.append(
                {
                    "entity_id": entity_id,
                    "entity_label": entity_labels.get(entity_id, entity_id),
                    "condition_id": condition_id,
                    "cell_n": cell_n,
                    "successes": successes,
                    "expected_successes": expected_successes,
                    "reference_probability": reference_probability,
                    "model_effect_logodds": model_effect,
                    "centered_effect_logodds": centered_effect,
                    "effect_logodds": effect,
                    "effect_logodds_sd": effect_sd,
                    "effect_logodds_low": effect_low,
                    "effect_logodds_high": effect_high,
                    "effect_probability": effect_probability,
                    "effect_probability_low": effect_probability_low,
                    "effect_probability_high": effect_probability_high,
                    "probability_practical": probability_practical,
                    "eligible": eligible,
                    "reliable": reliable,
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["reliable", "probability_practical", "cell_n"],
        ascending=[False, False, False],
        ignore_index=True,
    )


def _resolve_entity_labels(
    frame: pd.DataFrame,
    *,
    entity_col: str,
    entity_label_col: str | None,
) -> dict[str, str]:
    if entity_label_col is None:
        return {}
    labels = frame[[entity_col, entity_label_col]].dropna().copy()
    labels[entity_col] = labels[entity_col].astype("string")
    labels[entity_label_col] = labels[entity_label_col].astype("string")
    return {
        str(entity_id): str(group[entity_label_col].mode().iloc[0])
        for entity_id, group in labels.groupby(entity_col, observed=True)
        if not group.empty
    }


def _probability_shift(reference_probability: float, effect_logodds: float) -> float:
    base = float(np.clip(reference_probability, 1e-6, 1.0 - 1e-6))
    shifted = float(expit(_logit(np.asarray([base], dtype=float))[0] + effect_logodds))
    return shifted - base


def _probability_outside_practical_range(
    *,
    mean: float,
    sd: float,
    reference_probability: float,
    practical_delta_probability: float,
) -> float:
    base = float(np.clip(reference_probability, 1e-6, 1.0 - 1e-6))
    upper_probability = min(base + practical_delta_probability, 1.0 - 1e-6)
    lower_probability = max(base - practical_delta_probability, 1e-6)
    upper_logodds = float(_logit(np.asarray([upper_probability]))[0] - _logit(np.asarray([base]))[0])
    lower_logodds = float(_logit(np.asarray([lower_probability]))[0] - _logit(np.asarray([base]))[0])
    resolved_sd = max(float(sd), 1e-12)
    return float(
        norm.cdf(lower_logodds, loc=mean, scale=resolved_sd)
        + norm.sf(upper_logodds, loc=mean, scale=resolved_sd)
    )


def _logit(probability: np.ndarray) -> np.ndarray:
    values = np.clip(np.asarray(probability, dtype=float), 1e-12, 1.0 - 1e-12)
    return np.log(values / (1.0 - values))
