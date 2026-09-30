import numpy as np
import pytest
from pandas.testing import assert_frame_equal

from harp.core.calibration import calculate_calibration
from harp.core.odds_calibration import add_odds_band_report, validate_odds_entry_identity
from tests.calibration_support import odds_inputs, samples


def test_odds_boundary_equality_enters_upper_band_and_empty_bands_are_retained():
    report = calculate_calibration(samples([.1, .2, .3, .4, .5], [0, 1, 0, 1, 1]))
    result = add_odds_band_report(report, odds_inputs([1, 1.3999, 1.4, 1.8, 50]).odds,
                                  min_samples_per_bin=2)
    bands = result.odds_bands.metrics
    assert bands.samples.tolist() == [2, 1, 1, 0, 0, 0, 0, 1]
    assert bands.positives.tolist() == [1, 0, 1, 0, 0, 0, 0, 1]
    assert bands.loc[0, "brier"] == pytest.approx(.325)
    assert bands.loc[0, "auc"] == 1
    assert np.isnan(bands.loc[1, "auc"])
    assert bands.loc[1, "status"] == "small_sample"
    assert bands.loc[3, "status"] == "empty"
    assert result.odds_bands.coverage["available_samples"] == 5
    assert result.metrics == report.metrics


def test_missing_odds_preserve_overall_metrics_and_use_only_same_covered_population():
    report = calculate_calibration(samples([.1, .9, .5, .2], [0, 1, 1, 0]))
    # Entry 2 has a quote with a missing price; entry 4 is absent from the source entirely.
    result = add_odds_band_report(report, odds_inputs([2, np.nan, 4], numbers=[1, 2, 3]).odds)
    coverage = result.odds_bands.coverage
    assert coverage["available_samples"] == 2
    assert coverage["available_fraction"] == .5
    assert coverage["excluded_by_reason"] == {"unavailable": 1, "unmatched_entry": 1}
    assert coverage["matched_overall_metrics"]["brier"] == pytest.approx(.13)
    assert result.odds_bands.metrics.samples.sum() == 2
    assert result.metrics["samples"] == 4
    assert result.metrics == report.metrics
    assert_frame_equal(result.predictions, report.predictions)


def test_permuted_prediction_order_cannot_change_odds_band_membership():
    frame = samples([.1, .2, .8], [0, 0, 1])
    odds = odds_inputs([2, 6, 12]).odds
    first = add_odds_band_report(calculate_calibration(frame), odds)
    permuted = add_odds_band_report(calculate_calibration(frame.iloc[[2, 0, 1]]), odds)
    assert_frame_equal(first.odds_bands.metrics, permuted.odds_bands.metrics)


def test_all_missing_odds_produce_coverage_and_empty_band_rows():
    result = add_odds_band_report(calculate_calibration(samples([.1, .8], [0, 1])), odds_inputs([np.nan, np.nan]).odds)
    assert result.metrics["samples"] == 2
    assert result.odds_bands.coverage["status"] == "no_available_odds"
    assert result.odds_bands.coverage["matched_overall_metrics"] is None
    assert result.odds_bands.metrics.samples.sum() == 0
    assert result.odds_bands.bins.empty


@pytest.mark.parametrize("bounds", [(1, 2, 2, np.inf), (0, 2, np.inf), (1, 10), (1, np.nan, np.inf)])
def test_invalid_band_boundaries_fail_instead_of_silently_dropping_rows(bounds):
    with pytest.raises(ValueError, match="bounds"):
        add_odds_band_report(calculate_calibration(samples([.2], [0])), odds_inputs([2]).odds, bounds=bounds)


def test_odds_identity_bridge_rejects_a_different_horse_with_the_same_race_number():
    frame = samples([.2], [0])
    frame.loc[0, "kettonum"] = "different"
    with pytest.raises(ValueError, match="identity"):
        validate_odds_entry_identity(frame, odds_inputs([2]).frame)


def test_unknown_labels_are_excluded_from_both_coverage_and_band_statistics():
    result = add_odds_band_report(calculate_calibration(samples([.1, .8, .3], [0, 1, None])),
                                 odds_inputs([2, 3, np.nan]).odds)
    assert result.odds_bands.coverage["available_fraction"] == 1
    assert result.odds_bands.coverage["labelled_samples"] == 2
    assert result.metrics["excluded_missing_labels"] == 1


@pytest.mark.parametrize("market,method,expected", [("place", "low", [1, 0, 0]),
    ("place", "midpoint", [0, 1, 0]), ("place", "high", [0, 0, 1]), ("win", "midpoint", [0, 0, 1])])
def test_band_membership_uses_the_explicit_market_and_place_price_method(market, method, expected):
    from harp.core.odds import QUOTE_COLUMNS, select_odds
    original = odds_inputs([2])
    quotes = original.odds.frame[list(QUOTE_COLUMNS)].assign(win_odds=6., place_low=1., place_high=3.)
    odds = select_odds(original.frame, quotes, original.odds.policy)
    result = add_odds_band_report(calculate_calibration(samples([.2], [0])), odds,
                                  market=market, place_method=method, bounds=(1, 2, 3, np.inf))
    assert result.odds_bands.metrics.samples.tolist() == expected
