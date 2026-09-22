"""The same consumer contract against real SQL layouts, not canned SELECT results."""
import os
from datetime import UTC, datetime
from uuid import uuid4

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from harp.adapters.driven.db.race_input_repository import (
    RaceInputMapping,
    SqlRaceInputRepository,
)
from harp.core.odds import OddsContractError, OddsPolicy, assemble_odds_features
from harp.core.race_inputs import RaceInputQuery
from harp.interface.ports import InferenceRepositoryPort, TrainingRepositoryPort

AS_OF = datetime(2026, 6, 13, 6, tzinfo=UTC)


@pytest.fixture(params=["sqlite"] + (["postgres"] if os.environ.get("HARP_CONTRACT_TEST_DB_URL") else []))
def contract_engine(request):
    if request.param == "sqlite":
        engine = create_engine("sqlite://")
        yield engine
        engine.dispose()
        return
    url = os.environ["HARP_CONTRACT_TEST_DB_URL"]
    schema = "harp_contract_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-c search_path={schema}"})
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture(params=["original", "renamed", "split", "extra_columns", "typed"])
def provider(request, contract_engine):
    engine = contract_engine
    rows = pd.DataFrame({
        "race_id": ["R1", "R1", "R2"], "horse_number": [1, 2, 1],
        "held_date": ["2026-06-13"] * 3, "num_starters": [2, 2, 1],
        "scheduled_start_at": ["2026-06-13T06:10:00+00:00"] * 3,
        "speed": [0.1, 0.2, 0.8], "is_place": [1, 0, 1],
        "win_odds": [4.0, 5.0, 2.0], "place_low": [1.8, 2.2, 1.1],
        "place_high": [2.0, 2.6, 1.3], "win_popularity": [1, 2, 1],
        "published_at": ["2026-06-13T06:00:00+00:00"] * 3,
        "available_at": [None] * 3,
    })
    if request.param == "typed":
        from decimal import Decimal
        rows["held_date"] = pd.to_datetime(rows.held_date).dt.date
        for column in ["scheduled_start_at", "published_at"]:
            rows[column] = pd.to_datetime(rows[column], utc=True)
        # Numeric database types must not alter the logical prices or identities.
        rows["win_odds"] = rows.win_odds.map(lambda value: Decimal(str(value)))
    renamed = request.param in {"renamed", "split"}
    columns = {name: f"physical_{index}" if renamed else name for index, name in enumerate(rows.columns)}
    quotes_table = None
    odds_names = ["win_odds", "place_low", "place_high", "win_popularity", "published_at", "available_at"]
    from sqlalchemy import Numeric
    dtypes = {columns["win_odds"]: Numeric(12, 3)} if request.param == "typed" else None
    with engine.begin() as conn:
        if request.param == "extra_columns":
            rows["unrelated_new_column"] = "ignored"
        if request.param == "split":
            quotes_table = "market_ticks"
            rows[["race_id", "horse_number", *odds_names]].rename(columns=columns).to_sql(quotes_table, conn, index=False)
            base = rows.drop(columns=odds_names)
        else:
            base = rows
        base.rename(columns=columns).to_sql("entries_v2" if renamed else "entries", conn, index=False, dtype=dtypes)
    mapping = RaceInputMapping(
        entries_table="entries_v2" if renamed else "entries",
        entry_columns=columns,
        quote_columns=columns,
        quotes_table=quotes_table,
        naive_timestamp_timezone="UTC" if request.param == "typed" else None,
    )
    yield SqlRaceInputRepository(engine=engine, mapping=mapping), engine, mapping


def query(*, training=False, **kwargs):
    return RaceInputQuery("2026-06-13", "2026-06-13", ("speed", "log_odds_tansho"),
                          OddsPolicy.pre_start(max_age_seconds=300) if training else OddsPolicy.latest(AS_OF, 300),
                          target_names=("is_place",) if training else (), **kwargs)


@pytest.mark.parametrize("consumer", ["prediction", "training"])
def test_each_port_returns_the_same_semantics_across_schema_layouts(provider, consumer):
    repo, _, _ = provider
    if consumer == "prediction":
        port: InferenceRepositoryPort = repo
        result = port.load_prediction_input(query())
    else:
        port: TrainingRepositoryPort = repo
        result = port.load_training_input(query(training=True))
        assert result.frame.is_place.tolist() == [1, 1, 0]
    assert result.frame.race_id.tolist() == ["R2", "R1", "R1"]
    assert result.odds.frame.win_odds.tolist() == [2.0, 4.0, 5.0]
    assert assemble_odds_features(result.frame, result.odds).log_odds_tansho.tolist() == pytest.approx([0.69314718056, 1.38629436112, 1.60943791243])


def test_limit_preserves_complete_races(provider):
    repo, _, _ = provider
    result = repo.load_prediction_input(query(max_races=1))
    assert result.frame.race_id.tolist() == ["R2"]
    result = repo.load_prediction_input(query(max_races=2))
    assert result.frame.groupby("race_id").size().to_dict() == {"R1": 2, "R2": 1}


def test_missing_required_physical_column_is_a_port_contract_failure(provider):
    repo, engine, mapping = provider
    with engine.begin() as conn:
        conn.execute(text(f'ALTER TABLE "{mapping.entries_table}" RENAME COLUMN "{mapping.entry_columns["speed"]}" TO "unexpected_speed"'))
    with pytest.raises(OddsContractError, match="source schema"):
        repo.load_prediction_input(query())


def test_duplicate_base_entries_are_not_hidden_by_join_deduplication(provider):
    repo, engine, mapping = provider
    with engine.begin() as conn:
        conn.execute(text(f'INSERT INTO "{mapping.entries_table}" SELECT * FROM "{mapping.entries_table}" LIMIT 1'))
    with pytest.raises(OddsContractError, match="duplicate entry"):
        repo.load_prediction_input(query())


@pytest.mark.parametrize("training", [False, True])
def test_empty_input_is_a_valid_empty_batch(provider, training):
    repo, _, _ = provider
    result = (repo.load_training_input if training else repo.load_prediction_input)(
        query(training=training, filters={"speed__gt": 100}))
    assert result.frame.empty
    assert result.odds.frame.empty


def test_prediction_port_rejects_post_race_targets(provider):
    repo, _, _ = provider
    with pytest.raises(OddsContractError, match="post-race"):
        repo.load_prediction_input(query(training=True))


def test_sql_parameter_values_cannot_change_query_structure(provider):
    repo, _, _ = provider
    result = repo.load_prediction_input(query(filters={"race_id": "R1' OR 1=1 --"}))
    assert result.frame.empty


def test_numeric_feature_type_change_is_detected_at_the_port(provider):
    repo, engine, mapping = provider
    column = mapping.entry_columns["speed"]
    table = mapping.entries_table
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE TEXT USING "{column}"::text'))
        conn.execute(text(f'UPDATE "{table}" SET "{column}" = :value'), {"value": "not-a-number"})
    with pytest.raises(OddsContractError, match="numeric input"):
        repo.load_prediction_input(query())
