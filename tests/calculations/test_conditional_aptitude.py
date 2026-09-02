from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from harp.core.conditional_aptitude import (
    ConditionSpec,
    ConfirmationPolicy,
    NumericRange,
    block_bootstrap_mean,
    build_expanding_window_folds,
    confirm_pair,
    fit_empirical_bayes_interactions,
    fit_regularized_interaction_logistic,
    materialize_condition,
)
from harp.core.conditional_aptitude.regularized_logistic import binary_log_loss


def test_condition_materialization_is_driven_by_replaceable_specs() -> None:
    frame = pd.DataFrame(
        {
            "distance": [1200, 1800, 2400],
            "course": ["Tokyo", "Kyoto", "Tokyo"],
        }
    )
    distance = ConditionSpec(
        key="distance_band",
        source_cols=("distance",),
        transform="fixed_ranges",
        ranges=(
            NumericRange("short", upper=1599),
            NumericRange("middle", lower=1600, upper=2199),
            NumericRange("long", lower=2200),
        ),
    )
    course = ConditionSpec(key="course", source_cols=("course",))

    assert materialize_condition(frame, distance).tolist() == [
        "short",
        "middle",
        "long",
    ]
    assert materialize_condition(frame, course).tolist() == ["Tokyo", "Kyoto", "Tokyo"]

    ambiguous = pd.DataFrame(
        {
            "left": ["a | b", "a"],
            "right": ["c", "b | c"],
        }
    )
    crossed = ConditionSpec(
        key="crossed",
        source_cols=("left", "right"),
        transform="cross_category",
    )
    crossed_values = materialize_condition(ambiguous, crossed)
    assert crossed_values.nunique() == 2


def test_regularized_interaction_and_empirical_bayes_find_planted_pattern() -> None:
    frame = _planted_frame(n=1_200, seed=7)
    train = frame.iloc[:800]
    validation = frame.iloc[800:]
    m0 = fit_regularized_interaction_logistic(
        train,
        outcome_col="outcome",
        base_probability_col="base_probability",
        entity_col="entity_id",
        condition_col="condition_id",
        main_penalty=1.0,
        interaction_penalty=None,
    )
    m1 = fit_regularized_interaction_logistic(
        train,
        outcome_col="outcome",
        base_probability_col="base_probability",
        entity_col="entity_id",
        condition_col="condition_id",
        main_penalty=1.0,
        interaction_penalty=1.0,
    )
    y = validation["outcome"].to_numpy(dtype=float)
    kwargs = {
        "base_probability": validation["base_probability"].to_numpy(dtype=float),
        "entity": validation["entity_id"],
        "condition": validation["condition_id"],
    }
    assert binary_log_loss(y, m1.predict_proba(**kwargs)) < binary_log_loss(
        y, m0.predict_proba(**kwargs)
    )
    assert np.allclose(m1.interaction_effects.sum(axis=0), 0.0, atol=1e-10)
    assert np.allclose(m1.interaction_effects.sum(axis=1), 0.0, atol=1e-10)

    eb = fit_empirical_bayes_interactions(
        train,
        outcome_col="outcome",
        base_probability_col="base_probability",
        entity_col="entity_id",
        condition_col="condition_id",
        entity_label_col=None,
        main_penalty=1.0,
        min_entity_total_n=30,
        min_condition_levels=2,
        min_cell_n_for_claim=20,
        practical_delta_probability=0.01,
        local_probability_threshold=0.90,
    )
    effects = eb.cell_effects.set_index(["entity_id", "condition_id"])
    assert eb.model.tau_logodds > 0.1
    assert effects.loc[("e0", "c0"), "effect_logodds"] > 0.0
    assert effects.loc[("e0", "c1"), "effect_logodds"] < 0.0
    assert np.allclose(
        eb.cell_effects["effect_logodds"],
        eb.cell_effects["model_effect_logodds"],
    )
    assert "centered_effect_logodds" in eb.cell_effects


def test_interaction_contrasts_cannot_reproduce_pure_main_effects() -> None:
    rows: list[dict[str, object]] = []
    for entity, successes in (("e0", 8), ("e1", 2)):
        for condition in ("c0", "c1"):
            for row_idx in range(10):
                rows.append(
                    {
                        "entity_id": entity,
                        "condition_id": condition,
                        "base_probability": 0.5,
                        "outcome": int(row_idx < successes),
                    }
                )
    frame = pd.DataFrame(rows)
    model = fit_regularized_interaction_logistic(
        frame,
        outcome_col="outcome",
        base_probability_col="base_probability",
        entity_col="entity_id",
        condition_col="condition_id",
        main_penalty=1.0,
        interaction_penalty=0.1,
    )

    assert np.max(np.abs(model.interaction_effects)) < 1e-8
    assert np.allclose(model.interaction_effects.sum(axis=0), 0.0, atol=1e-12)
    assert np.allclose(model.interaction_effects.sum(axis=1), 0.0, atol=1e-12)


def test_prediction_normalizes_categories_like_training() -> None:
    frame = _planted_frame(n=400, seed=31)
    frame["entity_id"] = "  " + frame["entity_id"] + " "
    frame["condition_id"] = frame["condition_id"] + "  "
    model = fit_regularized_interaction_logistic(
        frame,
        outcome_col="outcome",
        base_probability_col="base_probability",
        entity_col="entity_id",
        condition_col="condition_id",
        main_penalty=1.0,
        interaction_penalty=1.0,
    )
    raw_probability = model.predict_proba(
        base_probability=frame["base_probability"].to_numpy(dtype=float),
        entity=frame["entity_id"],
        condition=frame["condition_id"],
    )
    stripped_probability = model.predict_proba(
        base_probability=frame["base_probability"].to_numpy(dtype=float),
        entity=frame["entity_id"].str.strip(),
        condition=frame["condition_id"].str.strip(),
    )

    assert np.allclose(raw_probability, stripped_probability)


def test_regularized_logistic_rejects_invalid_outcomes_and_nonconvergence() -> None:
    frame = _planted_frame(n=200, seed=13)
    invalid = frame.copy()
    invalid["outcome"] = invalid["outcome"].astype(float)
    invalid.loc[0, "outcome"] = 0.5
    with pytest.raises(ValueError, match="only 0 and 1"):
        fit_regularized_interaction_logistic(
            invalid,
            outcome_col="outcome",
            base_probability_col="base_probability",
            entity_col="entity_id",
            condition_col="condition_id",
            main_penalty=1.0,
            interaction_penalty=1.0,
        )

    with pytest.raises(RuntimeError, match="failed to converge"):
        fit_regularized_interaction_logistic(
            frame,
            outcome_col="outcome",
            base_probability_col="base_probability",
            entity_col="entity_id",
            condition_col="condition_id",
            main_penalty=1.0,
            interaction_penalty=0.1,
            max_iter=1,
        )


def test_time_folds_and_block_bootstrap_preserve_temporal_units() -> None:
    dates = pd.Series(pd.date_range("2020-01-01", periods=36, freq="MS"))
    folds = build_expanding_window_folds(
        dates,
        validation_start="2021-01-01",
        validation_end="2023-01-01",
        validation_months=6,
        step_months=6,
    )
    assert len(folds) == 4
    for fold in folds:
        assert dates.iloc[fold.train_positions].max() < dates.iloc[fold.validation_positions].min()

    interval = block_bootstrap_mean(
        np.array([-0.3, -0.2, -0.1, -0.4]),
        pd.Series(["w1", "w1", "w2", "w2"]),
        repetitions=200,
        confidence_level=0.95,
        random_seed=11,
    )
    assert interval.high < 0.0
    assert interval.probability_below_zero == 1.0

    with pytest.raises(ValueError, match="at least two distinct blocks"):
        block_bootstrap_mean(
            np.array([-0.3, -0.2]),
            pd.Series(["only", "only"]),
            repetitions=100,
            confidence_level=0.95,
            random_seed=11,
        )


def test_confirmation_is_inconclusive_when_too_few_time_folds_exist() -> None:
    frame = _planted_frame(n=120, seed=19)
    frame["race_id"] = np.arange(len(frame)).astype(str)
    frame["date"] = pd.date_range("2020-01-01", periods=len(frame), freq="D")
    result = confirm_pair(
        frame,
        pair_id="jockey__distance",
        validation_start="2020-03-01",
        validation_end="2020-05-01",
        practical_interaction_rms=0.05,
        policy=ConfirmationPolicy(
            validation_months=2,
            step_months=2,
            min_folds=2,
            bootstrap_repetitions=100,
        ),
    )

    assert result.summary["decision"] == "inconclusive"
    assert result.summary["inconclusive_reason"] == "insufficient_folds"
    assert result.oos_predictions.empty


def _planted_frame(*, n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    entity_idx = np.arange(n) % 2
    condition_idx = (np.arange(n) // 2) % 2
    interaction = np.where(entity_idx == condition_idx, 1.3, -1.3)
    base_probability = np.full(n, 0.20)
    base_logit = np.log(base_probability / (1.0 - base_probability))
    probability = 1.0 / (1.0 + np.exp(-(base_logit + interaction)))
    return pd.DataFrame(
        {
            "entity_id": np.where(entity_idx == 0, "e0", "e1"),
            "condition_id": np.where(condition_idx == 0, "c0", "c1"),
            "base_probability": base_probability,
            "outcome": rng.binomial(1, probability),
        }
    )
