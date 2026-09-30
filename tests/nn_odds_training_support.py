from dataclasses import asdict, replace
from unittest.mock import create_autospec

import numpy as np

from harp.core.nn.config import resolve_nn_training_recipe
from harp.core.nn.odds_targets import NnOddsSnapshot, select_nn_odds_reference
from harp.interface.ports.nn_odds_ports import NnOddsSnapshotStorePort
from tests.nn_odds_support import batch, quotes
from tests.nn_training_support import small_recipe, training_deps


def odds_recipe(weight=.1, **overrides):
    document = asdict(small_recipe(**overrides))
    document.update(version=3, auxiliary_odds={
        'name': 'huber_log_place_midpoint', 'weight': weight, 'reduction': 'available_entrant_mean'})
    return resolve_nn_training_recipe(document)


def odds_training_deps(source=None, *, future_log_odds=10., missing_train=False):
    deps, runs, tracking = training_deps(source)
    source = deps.input_store.load('a' * 64).inputs
    recipe = deps.prepared_store.load('b' * 64)
    reference = select_nn_odds_reference(source.inputs.entries, recipe.partitions)
    frame = quotes(reference)
    values = np.where(reference.split.eq('train'), np.where(reference.horse_number.eq(1), np.exp(1), np.exp(3)), np.exp(future_log_odds))
    frame['place_low'] = values
    frame['place_high'] = values
    if missing_train:
        frame.loc[reference.split.eq('train') & reference.horse_number.eq(2), 'place_low'] = np.nan
    snapshot = NnOddsSnapshot(reference, batch(frame), prepared_dataset_id='b' * 64, input_dataset_id='a' * 64)
    store = create_autospec(NnOddsSnapshotStorePort, instance=True, spec_set=True)
    store.load.return_value = snapshot
    return replace(deps, odds_store=store), runs, tracking, snapshot, reference
