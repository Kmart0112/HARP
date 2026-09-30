from dataclasses import dataclass

from harp.core.nn.odds_targets import (
    FinalPlaceOddsQuery,
    NnOddsSnapshot,
    select_nn_odds_reference,
)
from harp.interface.ports.nn_odds_ports import (
    FinalPlaceOddsRepositoryPort,
    NnOddsSnapshotStorePort,
)
from harp.interface.ports.nn_prepared_dataset_ports import NnPreparedDatasetStorePort
from harp.interface.ports.nn_storage_ports import NnDatasetStorePort


@dataclass(frozen=True)
class CaptureNnFinalOddsRequest:
    prepared_dataset_id: str


@dataclass(frozen=True)
class CaptureNnFinalOddsDeps:
    inputs: NnDatasetStorePort
    prepared: NnPreparedDatasetStorePort
    repository: FinalPlaceOddsRepositoryPort
    snapshots: NnOddsSnapshotStorePort


@dataclass(frozen=True)
class CaptureNnFinalOddsResult:
    snapshot_id: str
    prepared_dataset_id: str
    input_dataset_id: str
    entries: int
    races: int
    statuses: dict
    coverage: list[dict]


def run_capture_nn_final_odds_usecase(req: CaptureNnFinalOddsRequest,
                                     deps: CaptureNnFinalOddsDeps) -> CaptureNnFinalOddsResult:
    recipe = deps.prepared.load(req.prepared_dataset_id)
    inputs = deps.inputs.load(recipe.input_dataset_id).inputs
    reference = select_nn_odds_reference(inputs.inputs.entries, recipe.partitions)
    batch = deps.repository.load(FinalPlaceOddsQuery(reference[["race_id", "horse_number"]]))
    snapshot = NnOddsSnapshot(reference, batch, prepared_dataset_id=req.prepared_dataset_id,
                              input_dataset_id=recipe.input_dataset_id)
    identity = deps.snapshots.save(snapshot)
    frame = snapshot.frame
    return CaptureNnFinalOddsResult(identity, req.prepared_dataset_id, recipe.input_dataset_id,
                                   len(frame), int(frame.race_id.nunique()),
                                   {str(k): int(v) for k, v in frame.status.value_counts().items()},
                                   snapshot.coverage.to_dict("records"))
