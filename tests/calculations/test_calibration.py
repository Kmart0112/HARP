import numpy as np
import pandas as pd
import pytest

from harp.core.calibration import calculate_calibration


def test_uniform_bins_include_endpoints_and_counts_conserve_labelled_entries():
    report = calculate_calibration(pd.DataFrame({"probability": [0, .25, .5, .75, 1, .4],
                                                "y_true": [0, 0, 1, 1, 1, None]}), n_bins=2, strategy="uniform")
    assert report.bins["count"].tolist() == [3, 2]
    assert report.bins.mean_probability.tolist() == pytest.approx([.25, .875])
    assert report.bins.observed_rate.tolist() == pytest.approx([1/3, 1])
    assert report.metrics["samples"] == 5
    assert report.metrics["excluded_missing_labels"] == 1
    assert report.metrics["brier"] == pytest.approx(.075)
    assert report.histogram["count"].sum() == 5


def test_quantile_ties_stay_together_and_single_class_metrics_are_defined():
    report = calculate_calibration(pd.DataFrame({"probability": [.2]*4, "y_true": [0]*4}), n_bins=10)
    assert report.bins["count"].tolist() == [4]
    assert report.bins.observed_rate.tolist() == [0]
    assert report.metrics["brier"] == pytest.approx(.04)
    assert report.metrics["logloss"] == pytest.approx(.2231435513)


@pytest.mark.parametrize("probability,labels", [([np.nan], [1]), ([np.inf], [0]),
                          ([-.01], [0]), ([1.01], [1]), ([.3], [.5]), ([.4], [None]), ([], [])])
def test_invalid_predictions_labels_or_empty_evaluation_are_rejected(probability, labels):
    with pytest.raises(ValueError):
        calculate_calibration(pd.DataFrame({"probability": probability, "y_true": labels}))


def test_duplicate_entrant_identity_is_not_counted_twice():
    with pytest.raises(ValueError, match="unique"):
        calculate_calibration(pd.DataFrame({"race_id": ["r", "r"], "kettonum": ["h", "h"],
                                            "y_true": [0, 1], "probability": [.2, .3]}))
