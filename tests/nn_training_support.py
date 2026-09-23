from dataclasses import asdict
from copy import deepcopy
from unittest.mock import create_autospec

import pytest
import torch

from harp.core.nn.config import resolve_nn_training_recipe
from harp.core.nn.dataset import prepare_nn_dataset
from harp.core.nn.split import NnDatasetConfig
from harp.interface.ports.nn_prepared_dataset_ports import NnPreparedDatasetRecipe, NnPreparedDatasetStorePort
from harp.interface.ports.nn_storage_ports import NnDatasetStorePort, StoredNnDataset
from harp.interface.ports.nn_training_ports import NnModelStorePort, StoredNnCheckpoint
from harp.interface.ports.tracking_ports import TrackingPort
from harp.usecase.training.nn_dto import NnTrainDeps
from tests.nn_dataset_support import dataset_inputs


@pytest.fixture(autouse=True)
def torch_cpu_runtime():
    original = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(original)


def small_recipe(**overrides):
    return resolve_nn_training_recipe({
        "version": 1,
        "model": dict(name="history_set_transformer_v1", d_model=16, categorical_embedding_dim=3,
                      history_layers=1, race_layers=1, attention_heads=2, feedforward_dim=24, dropout=0.0),
        "optimizer": dict(name="adamw", lr=.02, weight_decay=.001),
        "scheduler": dict(name="reduce_on_plateau", factor=.5, patience=2, min_lr=.00001),
        "training": dict(batch_size_races=2, max_epochs=3, seed=17, gradient_clip_norm=1.0),
        "loss": dict(name="bce_with_logits", reduction="entrant_mean"),
        "early_stopping": dict(metric="validation.logloss", mode="min", patience=3, min_delta=.0001),
        "runtime": dict(device="cpu", precision="float32", num_workers=0, num_threads=1),
    }, overrides)


def small_prepared(inputs=None):
    return prepare_nn_dataset(inputs or dataset_inputs(future_rate=.4), NnDatasetConfig("2026-06-13", "2026-06-20", 3))


def training_deps(inputs=None, config=None):
    inputs = inputs or dataset_inputs(future_rate=.4)
    prepared = prepare_nn_dataset(inputs, config or NnDatasetConfig("2026-06-13", "2026-06-20", 3))
    input_store = create_autospec(NnDatasetStorePort, instance=True, spec_set=True)
    input_store.load.return_value = StoredNnDataset(inputs, {})
    prepared_store = create_autospec(NnPreparedDatasetStorePort, instance=True, spec_set=True)
    prepared_store.load.return_value = NnPreparedDatasetRecipe("a" * 64, prepared.config, prepared.preprocessing, prepared.partitions)
    model_store = create_autospec(NnModelStorePort, instance=True, spec_set=True)
    tracking = create_autospec(TrackingPort, instance=True, spec_set=True)
    runs, tracking_state = {}, {}

    def create_run(metadata):
        identity = f"{len(runs) + 1:032x}"
        runs[identity] = {"metadata": deepcopy(metadata), "checkpoints": {}}
        return identity

    def save(run_id, checkpoint):
        identity = f"{checkpoint['epoch']:064x}"
        runs[run_id]["checkpoints"][identity] = deepcopy(checkpoint)
        return identity

    def load(run_id, checkpoint_id=None):
        run = runs[run_id]
        checkpoint_id = checkpoint_id or next(reversed(run["checkpoints"]))
        metadata = deepcopy(run["metadata"])
        return StoredNnCheckpoint(run_id, checkpoint_id, metadata, deepcopy(run["checkpoints"][checkpoint_id]),
                                  "/fake/artifact", resolve_nn_training_recipe(metadata["recipe"]), prepared.preprocessing)

    model_store.create_run.side_effect = create_run
    model_store.save_checkpoint.side_effect = save
    model_store.load_checkpoint.side_effect = load
    tracking.start_run.return_value = "tracking-run"
    tracking.set_terminated.side_effect = lambda run_id, status: tracking_state.update(status=status)
    tracking.log_metrics.side_effect = lambda run_id, metrics, step=None: tracking_state.setdefault("metrics", []).append((step, metrics))
    return NnTrainDeps(input_store, prepared_store, model_store, tracking), runs, tracking_state
