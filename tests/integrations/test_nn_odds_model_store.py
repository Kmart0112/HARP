from dataclasses import asdict, replace

import numpy as np
import pytest
import yaml

pytest.importorskip('torch')

from harp.adapters.driven.storage.nn_dataset_store import ParquetNnDatasetStore
from harp.adapters.driven.storage.nn_model_store import TorchNnModelStore
from harp.adapters.driven.storage.nn_odds_snapshot_store import (
    ParquetNnOddsSnapshotStore,
)
from harp.adapters.driven.storage.nn_prepared_dataset_store import (
    JsonNnPreparedDatasetStore,
)
from harp.controllers.calibration import export_calibration_report
from harp.controllers.training.nn import NnTrainCommand, NnTrainController
from harp.core.nn.config import NnAuxiliaryRankConfig
from harp.core.nn.odds_targets import NnOddsSnapshot
from harp.interface.ports.nn_prepared_dataset_ports import NnPreparedDatasetRecipe
from harp.usecase.prediction.nn import load_nn_predictor
from tests.nn_odds_support import batch, quotes
from tests.nn_odds_training_support import odds_recipe, odds_training_deps
from tests.nn_training_support import small_prepared


@pytest.mark.parametrize('with_rank', [False, True])
def test_odds_bundle_replays_targets_and_restores_predictions_without_db(tmp_path, with_rank):
    deps, _, _, _, reference = odds_training_deps()
    source = deps.input_store.load('a' * 64).inputs
    prepared = small_prepared(source)
    input_root, prepared_root, model_root, odds_root = [tmp_path / name for name in ('inputs', 'datasets', 'models', 'odds')]
    input_id = ParquetNnDatasetStore(input_root).save(source, {})
    dataset_id = JsonNnPreparedDatasetStore(prepared_root).save(NnPreparedDatasetRecipe(
        input_id, prepared.config, prepared.preprocessing, prepared.partitions))
    frame = quotes(reference)
    frame['place_low'] = [1., 3., 2., 10.]
    frame['place_high'] = [2., 4., 3., 20.]
    snapshot = NnOddsSnapshot(reference, batch(frame), prepared_dataset_id=dataset_id, input_dataset_id=input_id)
    odds_id = ParquetNnOddsSnapshotStore(odds_root).save(snapshot)
    recipe_path = tmp_path / 'recipe.yml'
    recipe = odds_recipe()
    if with_rank:
        recipe = replace(recipe, auxiliary_rank=NnAuxiliaryRankConfig('pairwise_logistic', .3, 'race_mean', 'ignore'))
    recipe_path.write_text(yaml.safe_dump(asdict(recipe)))
    controller = NnTrainController(str(input_root), str(prepared_root), str(model_root), odds_root=str(odds_root), provenance={'source': 'fixture'})
    result = controller.run(NnTrainCommand(dataset_id, str(recipe_path), odds_snapshot_id=odds_id))
    evaluated = controller.evaluate(result.run_id)
    assert evaluated.metrics['odds_entries'] == 1
    store = TorchNnModelStore(model_root)
    saved = store.load_checkpoint(result.run_id)
    assert saved.metadata['odds_target']['snapshot_id'] == odds_id
    predictor = load_nn_predictor(result.run_id, store)
    expected = predictor.predict(source.inputs)
    # Main-task inference and calibration require no odds source or teacher store.
    (odds_root / odds_id).rename(odds_root / 'temporarily-unavailable')
    replay = load_nn_predictor(result.run_id, TorchNnModelStore(model_root)).predict(source.inputs)
    np.testing.assert_array_equal(replay.place_probability, expected.place_probability)
    report = export_calibration_report(model=result.run_id, dataset=dataset_id, backend='nn', split='test',
        output_dir=tmp_path / 'report', input_root=input_root, prepared_root=prepared_root, model_root=model_root)
    assert report.report.metrics['samples'] == 1
    assert (tmp_path / 'report/calibration.png').is_file()
