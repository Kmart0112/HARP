"""Explicit opponent-context examples, including a real run with unknown rates."""
from dataclasses import replace

from harp.core.nn.contracts import NnFeatureField, NnRaceInputs, NnTrainingInputs
from tests.nn_dataset_support import dataset_inputs


def opponent_inputs(*, future_rate=.75):
    original = dataset_inputs(future_rate=.4)
    base = original.inputs
    history = base.history
    values = {
        "opp_count": [2, 2, 2],
        "opp_horse_place_mean": [.5, None, future_rate],
        "opp_horse_place_top3_mean": [.5, None, future_rate],
        "opp_horse_place_std": [.25, None, 0],
        "opp_horse_starts_mean": [6, None, 4],
        "opp_horse_place_coverage": [1, 0, 1],
        "opp_jockey_place_mean": [.25, .375, None],
        "opp_jockey_place_top3_mean": [.25, .375, None],
        "opp_jockey_starts_mean": [12, 16, None],
        "opp_jockey_place_coverage": [1, .5, 0],
    }
    for name, column in values.items():
        history[name] = column
    contract = replace(base.contract, history_context=tuple(NnFeatureField(name, "numeric") for name in values))
    query = replace(base.query, history_context_names=tuple(values))
    inputs = NnRaceInputs(base.entries, history, query=query, contract=contract,
                         source_revision=base.source_revision, captured_at=base.captured_at)
    return NnTrainingInputs(inputs, original.targets)
