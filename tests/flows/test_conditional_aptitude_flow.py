from __future__ import annotations

from unittest.mock import create_autospec

import numpy as np
import pandas as pd

from harp.core.conditional_aptitude import (
    ConditionSpec,
    ConfirmationPolicy,
    EntitySpec,
    ObservationSchema,
    ScreeningPolicy,
)
from harp.interface.ports import (
    ConditionalAptitudeObservationRepositoryPort,
    ConditionalAptitudeProbabilityProviderPort,
)
from harp.usecase.conditional_aptitude import (
    ConditionalAptitudeDeps,
    ConditionalAptitudeRequest,
    run_conditional_aptitude_usecase,
)


def test_usecase_scans_replaceable_pairs_and_confirms_top_candidate() -> None:
    observations, probabilities = _flow_data()
    observation_repository = create_autospec(
        ConditionalAptitudeObservationRepositoryPort,
        instance=True,
        spec_set=True,
    )
    observation_repository.load_observations.return_value = observations
    probability_provider = create_autospec(
        ConditionalAptitudeProbabilityProviderPort,
        instance=True,
        spec_set=True,
    )
    probability_provider.load_base_probabilities.return_value = probabilities
    request = ConditionalAptitudeRequest(
        analysis_id="aptitude-smoke",
        from_date="2020-01-01",
        discovery_end="2022-01-01",
        confirmation_start="2023-01-01",
        to_date="2025-01-01",
        schema=ObservationSchema(
            key_cols=("entry_id",),
            race_id_col="race_id",
            date_col="race_date",
            outcome_col="is_place",
        ),
        entities=(
            EntitySpec("jockey", "jockey_id", min_total_n=30),
            EntitySpec("sire", "sire_id", min_total_n=30),
        ),
        conditions=(ConditionSpec("distance", ("distance_band",)),),
        screening_policy=ScreeningPolicy(
            min_cell_n_for_claim=15,
            min_eligible_coverage=0.8,
            practical_delta_probability=0.01,
            local_probability_threshold=0.85,
            top_k=1,
        ),
        confirmation_policy=ConfirmationPolicy(
            validation_months=6,
            step_months=6,
            tuning_months=6,
            interaction_penalty_grid=(0.5, 5.0),
            bootstrap_repetitions=100,
            practical_delta_probability=0.01,
            min_fold_win_rate=0.5,
            random_seed=9,
        ),
    )
    result = run_conditional_aptitude_usecase(
        request,
        ConditionalAptitudeDeps(
            observation_repository=observation_repository,
            probability_provider=probability_provider,
        ),
    )

    assert set(result.scan_summary["pair_id"]) == {
        "jockey__distance",
        "sire__distance",
    }
    assert result.selected_pair_ids == ("jockey__distance",)
    assert not result.confirmation_summary.empty
    assert set(result.fold_metrics["pair_id"]) == {"jockey__distance"}
    assert result.oos_predictions["date"].min() >= pd.Timestamp("2023-01-01")
    assert not result.confirmation_cell_stability.empty
    observation_repository.load_observations.assert_called_once()
    probability_provider.load_base_probabilities.assert_called_once()


def _flow_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    n = 2_080
    rng = np.random.default_rng(23)
    entry = np.arange(n)
    jockey = entry % 2
    distance = (entry // 2) % 2
    sire = (entry // 7) % 3
    interaction = np.where(jockey == distance, 1.4, -1.4)
    base_probability = np.full(n, 0.20)
    base_logit = np.log(base_probability / (1.0 - base_probability))
    probability = 1.0 / (1.0 + np.exp(-(base_logit + interaction)))
    observations = pd.DataFrame(
        {
            "entry_id": entry,
            "race_id": entry // 8,
            "race_date": pd.date_range("2020-01-01", periods=n, freq="21h"),
            "is_place": rng.binomial(1, probability),
            "jockey_id": np.where(jockey == 0, "j0", "j1"),
            "sire_id": np.where(sire == 0, "s0", np.where(sire == 1, "s1", "s2")),
            "distance_band": np.where(distance == 0, "short", "long"),
        }
    )
    probabilities = pd.DataFrame(
        {"entry_id": entry, "base_probability": base_probability}
    )
    return observations, probabilities
