from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from harp.core.odds import (
    OddsContractError,
    OddsPolicy,
    assemble_odds_features,
    select_odds,
)

DECISION = datetime(2026, 6, 13, 6, 0, tzinfo=UTC)


def entries() -> pd.DataFrame:
    return pd.DataFrame({
        "race_id": ["R1", "R1"], "horse_number": [1, 2],
        "scheduled_start_at": [DECISION + timedelta(minutes=10)] * 2,
        "num_starters": [2, 2],
    })


def quotes() -> pd.DataFrame:
    return pd.DataFrame({
        "race_id": ["R1", "R1"], "horse_number": [1, 2],
        "win_odds": [4.0, 5.0], "place_low": [1.8, 2.2],
        "place_high": [2.0, 2.6], "win_popularity": [1, 2],
        "published_at": [DECISION] * 2, "available_at": [None, None],
    })


@pytest.mark.parametrize("seconds,expected", [(-1, 4.0), (0, 4.0), (1, None)])
def test_latest_before_cutoff_is_inclusive(seconds, expected):
    source = quotes().iloc[:1].copy()
    source["published_at"] = DECISION + timedelta(seconds=seconds)
    batch = select_odds(entries(), source, OddsPolicy.latest(DECISION, max_age_seconds=300))
    actual = batch.frame.iloc[0]
    if expected is None:
        assert actual.win_status == "missing"
    else:
        assert actual.win_odds == expected
    assert len(batch.frame) == 2


@pytest.mark.parametrize("age,expected", [(299, "available"), (300, "available"), (301, "stale")])
def test_freshness_boundary_is_measured_against_cutoff(age, expected):
    source = quotes()
    source["published_at"] = DECISION - timedelta(seconds=age)
    batch = select_odds(entries(), source, OddsPolicy.pre_start(minutes=10, max_age_seconds=300))
    assert batch.frame.win_status.tolist() == [expected, expected]


def test_latest_unavailable_quote_does_not_resurrect_older_price():
    older = quotes()
    older["published_at"] = DECISION - timedelta(minutes=1)
    latest = quotes()
    latest.loc[0, "win_odds"] = None
    batch = select_odds(entries(), pd.concat([older, latest]), OddsPolicy.latest(DECISION, 300))
    assert batch.frame.iloc[0].win_status == "unavailable"
    assert batch.frame.iloc[0].place_status == "available"


def test_received_after_decision_is_not_known_at_decision():
    source = quotes()
    source["available_at"] = DECISION + timedelta(seconds=1)
    batch = select_odds(entries(), source, OddsPolicy.latest(DECISION, 300))
    assert batch.frame.win_status.tolist() == ["missing", "missing"]


def test_unknown_receipt_is_explicit_and_strict_replay_rejects_it():
    batch = select_odds(entries(), quotes(), OddsPolicy.latest(DECISION, 300))
    assert batch.availability_basis == "publication_time"
    with pytest.raises(OddsContractError, match="available_at"):
        select_odds(entries(), quotes(), OddsPolicy.latest(DECISION, 300, require_availability=True))


@pytest.mark.parametrize("fault", ["missing_column", "duplicate_entry", "conflicting_quote", "naive_time"])
def test_broken_contracts_are_rejected(fault):
    target, source = entries(), quotes()
    if fault == "missing_column":
        source = source.drop(columns="place_high")
    elif fault == "duplicate_entry":
        target = pd.concat([target, target.iloc[:1]])
    elif fault == "conflicting_quote":
        conflict = source.iloc[:1].copy()
        conflict["win_odds"] = 9
        source = pd.concat([source, conflict])
    else:
        source["published_at"] = DECISION.replace(tzinfo=None)
    with pytest.raises(OddsContractError):
        select_odds(target, source, OddsPolicy.latest(DECISION, 300))


def test_features_and_quote_identity_survive_reordering_and_share_the_same_odds():
    target = entries()
    batch = select_odds(target, quotes().iloc[::-1], OddsPolicy.latest(DECISION, 300))
    source_features = target.assign(speed=[3.0, 5.0], odds_tansho=999, log_odds_tansho=999)
    features = assemble_odds_features(source_features, batch)
    assert features.odds_tansho.tolist() == [4.0, 5.0]
    assert features.log_odds_tansho.tolist() == pytest.approx([1.38629436112, 1.60943791243])
    assert features.popularity_ratio.tolist() == [0.5, 1.0]
    other = select_odds(target.iloc[::-1], quotes(), OddsPolicy.latest(DECISION, 300))
    assert batch.frame.set_index("horse_number").quote_id.to_dict() == other.frame.set_index("horse_number").quote_id.to_dict()


def test_missing_scheduled_time_is_retained_as_unknown_cutoff():
    entries = pd.DataFrame({"race_id": ["R"], "horse_number": [1], "scheduled_start_at": [None]})
    quotes = pd.DataFrame({"race_id": ["R"], "horse_number": [1], "win_odds": [4.],
                           "place_low": [1.8], "place_high": [2.], "win_popularity": [1],
                           "published_at": ["2026-06-13T06:00:00+00:00"], "available_at": [None]})
    result = select_odds(entries, quotes, OddsPolicy.pre_start(max_age_seconds=300))
    assert result.frame.win_status.tolist() == ["unknown_cutoff"]
    assert result.frame.place_status.tolist() == ["unknown_cutoff"]
    assert result.frame.quote_id.isna().all()


def test_popularity_features_have_their_own_missing_value_contract():
    from harp.core.odds import odds_features_available
    source = quotes()
    source.loc[0, "win_odds"] = None
    source["win_popularity"] = source.win_popularity.astype(float)
    source.loc[1, "win_popularity"] = 1.5
    batch = select_odds(entries(), source, OddsPolicy.latest(DECISION, 300))
    frame = assemble_odds_features(entries(), batch)
    assert odds_features_available(frame, ["popularity"]).tolist() == [True, False]
    assert odds_features_available(frame, ["log_odds_tansho"]).tolist() == [False, True]
    assert frame.popularity_ratio.iloc[0] == 0.5
