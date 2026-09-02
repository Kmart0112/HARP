from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from harp.core.feature_validation_decision import (
    ValidationMetricSnapshot,
    decide_scenario_validation,
)
from harp.core.inference.ev_calculator import join_odds_and_compute_ev
from harp.core.training import apply_logit_shift_grouped


def test_ev_and_kelly_transform_probabilities_and_market_odds_into_a_capped_stake() -> None:
    predictions = pd.DataFrame(
        {
            "race_id": ["R1"],
            "horse_number": [1],
            "p_place": [0.60],
        }
    )
    odds = pd.DataFrame(
        {
            "race_id": ["R1"],
            "horse_number": [1],
            "odds_fukusho_low": [3.0],
            "odds_fukusho_high": [3.0],
            "odds_fukusho_avg": [3.0],
            "odds_fukusho_weighted_avg": [2.8],
        }
    )

    result = join_odds_and_compute_ev(
        df_pred=predictions,
        df_odds=odds,
        bankroll=2000.0,
        kelly_fraction=1.0,
        kelly_cap=0.05,
    ).iloc[0]

    assert float(result["edge"]) == pytest.approx(0.3333333333)
    assert float(result["kelly_fraction"]) == pytest.approx(0.05)
    assert float(result["kelly_bet_amount"]) == pytest.approx(100.0)


def test_race_local_probability_shift_matches_each_race_target_without_reordering_rows() -> None:
    probabilities = np.array([0.2, 0.8, 0.4, 0.7, 0.1], dtype=float)
    race_ids = np.array(["R2", "R1", "R2", "R1", "R2"], dtype=object)

    shifted = apply_logit_shift_grouped(
        probabilities,
        race_ids,
        k_by_group={"R1": 1.0, "R2": 1.5},
    )

    assert shifted.shape == probabilities.shape
    assert shifted[race_ids == "R1"].sum() == pytest.approx(1.0)
    assert shifted[race_ids == "R2"].sum() == pytest.approx(1.5)
    assert np.array_equal(np.argsort(probabilities[race_ids == "R2"]), np.argsort(shifted[race_ids == "R2"]))


def test_validation_decision_combines_metric_improvement_with_the_shap_guardrail() -> None:
    result = decide_scenario_validation(
        scenario_name="add_turn_direction",
        metrics=ValidationMetricSnapshot(auc=0.62, logloss=0.38, brier=0.18),
        baseline_metrics=ValidationMetricSnapshot(auc=0.60, logloss=0.40, brier=0.20),
        shap_judgement="懸念あり",
    )

    assert result.metrics_judgement == "improved"
    assert result.decision == "保留"
    assert result.final_recommendation == "hold"
