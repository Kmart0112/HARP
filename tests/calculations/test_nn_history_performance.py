import numpy as np

from harp.core.nn.dataset import prepare_nn_dataset
from harp.core.nn.split import NnDatasetConfig
from tests.nn_opponent_support import opponent_inputs
from tests.nn_performance_support import performance_inputs


def test_performance_metrics_preserve_fields_history_and_missing_runs():
    config = NnDatasetConfig("2026-06-13", "2026-06-20", 3)
    baseline = prepare_nn_dataset(opponent_inputs(), config)
    enriched = prepare_nn_dataset(performance_inputs(), config)
    assert enriched.preprocessing.current == baseline.preprocessing.current
    assert enriched.partitions == baseline.partitions
    assert len(enriched.preprocessing.history.numeric) == len(baseline.preprocessing.history.numeric) + 2
    sample = enriched.split("train")[0]
    np.testing.assert_array_equal(sample["history_mask"], baseline.split("train")[0]["history_mask"])
    names = enriched.preprocessing.history.numeric_names
    time = names.index("time_vs_avg")
    synergy = names.index("pos4_agari_synergy")
    np.testing.assert_array_equal(sample["history_numeric_missing"][0, :, time], [False, True, False])
    np.testing.assert_allclose(sample["history_numeric"][0, :, synergy], [-1, 1, 0])
    assert sample["history_mask"][0, 1]  # A missing result is a real run, not padding.
    assert not sample["history_mask"][1].any()  # New horse remains in the field.
    assert np.isfinite(sample["history_numeric"]).all()


def test_current_race_metrics_do_not_fit_or_enter_its_own_history():
    config = NnDatasetConfig("2026-06-13", "2026-06-20", 3)
    original = prepare_nn_dataset(performance_inputs(future_value=9), config)
    changed = prepare_nn_dataset(performance_inputs(future_value=9000), config)
    assert original.preprocessing == changed.preprocessing
    np.testing.assert_array_equal(original.split("train")[0]["history_numeric"],
                                  changed.split("train")[0]["history_numeric"])
    assert not np.array_equal(original.split("validation")[0]["history_numeric"],
                              changed.split("validation")[0]["history_numeric"])
