"""Per-run performance metrics alongside existing opponent context."""
from dataclasses import replace

from harp.core.nn.contracts import NnFeatureField, NnRaceInputs, NnTrainingInputs
from tests.nn_opponent_support import opponent_inputs


def performance_inputs(*, future_value=9.0):
    original = opponent_inputs()
    base = original.inputs
    history = base.history
    history["time_vs_avg"] = [-1.25, None, future_value]
    history["pos4_agari_synergy"] = [-0.5, 0.5, future_value]
    fields = tuple(NnFeatureField(name, "numeric") for name in ("time_vs_avg", "pos4_agari_synergy"))
    contract = replace(base.contract, history_results=(*base.contract.history_results, *fields))
    query = replace(base.query, history_result_names=contract.history_result_names)
    inputs = NnRaceInputs(base.entries, history, query=query, contract=contract,
                         source_revision=base.source_revision, captured_at=base.captured_at)
    return NnTrainingInputs(inputs, original.targets)
