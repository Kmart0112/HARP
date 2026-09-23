"""The NN input Port across SQL schemas, retaining full fields and past-run identities."""
import os
from uuid import uuid4

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from harp.adapters.driven.db.nn_input_repository import NnInputMapping, SqlNnInputRepository
from harp.core.nn.contracts import NnInputContractError
from harp.interface.ports.nn_input_ports import NnInputRepositoryPort
from tests.nn_input_support import feature_contract, input_query, input_tables


@pytest.fixture(params=["sqlite"] + (["postgres"] if os.environ.get("HARP_CONTRACT_TEST_DB_URL") else []))
def nn_engine(request):
    if request.param == "sqlite":
        engine = create_engine("sqlite://")
        try:
            yield engine
        finally:
            engine.dispose()
        return
    url = os.environ["HARP_CONTRACT_TEST_DB_URL"]
    schema = "harp_nn_contract_" + uuid4().hex
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


@pytest.fixture(params=["original", "renamed", "extra_columns", "typed"])
def nn_provider(request, nn_engine):
    tables = input_tables()
    mappings = []
    with nn_engine.begin() as conn:
        for table, frame in zip(("entrants", "past_runs", "outcomes"), tables):
            frame = frame.copy()
            columns = {name: f"field_{i}" if request.param == "renamed" else name
                       for i, name in enumerate(frame.columns)}
            mappings.append(columns)
            if request.param == "typed" and "held_date" in frame:
                frame["held_date"] = pd.to_datetime(frame.held_date).dt.date
                frame["age"] = frame.age.astype(str)
                frame["sex_cd"] = frame.sex_cd.astype(int)
            if request.param == "extra_columns":
                frame["jockey_id"] = 42
                frame["final_odds"] = 1.1
            frame.rename(columns=columns).to_sql(table, conn, index=False)
    mapping = NnInputMapping("entrants", "past_runs", "outcomes", *mappings)
    port: NnInputRepositoryPort = SqlNnInputRepository(engine=nn_engine, mapping=mapping, contract=feature_contract())
    return port, nn_engine, mapping


def test_longitudinal_port_preserves_fields_and_deduplicates_shared_history(nn_provider):
    port, _, _ = nn_provider
    result = port.load_training_inputs(input_query())
    assert result.inputs.entries.race_id.tolist() == ["R2", "R2", "R3"]
    assert result.inputs.entries.history_end_no.tolist() == [2, 0, 3]
    assert result.inputs.history.race_id.tolist() == ["R0", "R1", "R2"]
    assert result.inputs.history.jockey_place_rate_3y_smooth.tolist() == pytest.approx([.1, .2, .3])
    assert result.inputs.entries.sex_cd.tolist() == ["1", "1", "1"]
    assert result.inputs.entries.age.tolist() == [3., 3., 3.]
    assert pd.isna(result.inputs.entries.iloc[1].jockey_place_rate_3y_smooth)
    assert pd.isna(result.targets.iloc[1].is_place)  # Unknown is not a losing label.
    assert pd.isna(result.inputs.history.iloc[1].result_order)  # DNF remains in history.
    assert "result_order" not in result.inputs.entries
    assert "final_odds" not in result.inputs.entries


def test_limit_and_dates_select_whole_races_and_exclude_same_day_history(nn_provider):
    port, _, _ = nn_provider
    result = port.load_prediction_inputs(input_query(max_races=1))
    assert result.entries.kettonum.tolist() == ["H1", "H2"]
    assert result.history.race_id.tolist() == ["R0", "R1"]
    assert result.history.held_date.max() < result.entries.held_date.min()


def test_prediction_does_not_depend_on_a_current_result_table(nn_provider):
    port, engine, mapping = nn_provider
    with engine.begin() as conn:
        conn.execute(text(f'DROP TABLE "{mapping.targets_table}"'))
    assert len(port.load_prediction_inputs(input_query()).entries) == 3


def test_zero_finishing_position_is_unknown_even_if_legacy_mart_marks_it_placed(nn_provider):
    port, engine, mapping = nn_provider
    target, past = mapping.target_columns, mapping.history_columns
    with engine.begin() as conn:
        conn.execute(text(f'''UPDATE "{mapping.targets_table}"
            SET "{target['result_order']}" = 0, "{target['is_place']}" = 1
            WHERE "{target['race_id']}" = 'R2' '''))
        conn.execute(text(f'''UPDATE "{mapping.history_table}"
            SET "{past['result_order']}" = 0 WHERE "{past['race_id']}" = 'R0' '''))
    result = port.load_training_inputs(input_query())
    assert result.inputs.entries.race_id.tolist() == ["R2", "R2", "R3"]
    assert result.targets.loc[result.targets.race_id == "R2", ["result_order", "is_win", "is_place"]].isna().all().all()
    assert result.inputs.history.loc[result.inputs.history.race_id == "R0", "result_order"].isna().all()
    assert result.targets.loc[result.targets.race_id == "R3", "is_place"].tolist() == [True]


def test_empty_period_is_a_valid_empty_training_input(nn_provider):
    port, _, _ = nn_provider
    result = port.load_training_inputs(input_query(from_date="2025-01-01", to_date="2025-12-31"))
    assert result.inputs.entries.empty and result.inputs.history.empty and result.targets.empty


@pytest.mark.parametrize("field", ["result_order", "jockey_id", "race_id"])
def test_current_feature_allowlist_rejects_labels_and_identities(nn_provider, field):
    port, _, _ = nn_provider
    with pytest.raises(NnInputContractError, match="not allowed"):
        port.load_prediction_inputs(input_query(feature_names=(field,)))


@pytest.mark.parametrize("fault,message", [
    ("missing_feature", "source schema"), ("duplicate_entry", "duplicate entry"),
    ("missing_horse", "incomplete race"), ("history_gap", "consecutive"),
    ("duplicate_history", "duplicate entry"), ("stale_endpoint", "stale history"),
    ("wrong_endpoint_id", "endpoint identity"), ("duplicate_target", "duplicate target"),
])
def test_invalid_source_is_rejected_at_the_port(nn_provider, fault, message):
    port, engine, mapping = nn_provider
    e, h = mapping.entry_columns, mapping.history_columns
    with engine.begin() as conn:
        statements = {
            "missing_feature": f'ALTER TABLE entrants RENAME COLUMN "{e["age"]}" TO unexpected_age',
            "duplicate_entry": 'INSERT INTO entrants SELECT * FROM entrants LIMIT 1',
            "missing_horse": f'DELETE FROM entrants WHERE "{e["kettonum"]}" = \'H2\'',
            "history_gap": f'DELETE FROM past_runs WHERE "{h["race_id"]}" = \'R0\'',
            "duplicate_history": f'INSERT INTO past_runs SELECT * FROM past_runs WHERE "{h["race_id"]}" = \'R0\'',
            "stale_endpoint": f'UPDATE past_runs SET "{h["held_date"]}" = \'2026-06-12\' WHERE "{h["race_id"]}" = \'R2\'',
            "wrong_endpoint_id": f'UPDATE entrants SET "{e["last_history_race_id"]}" = \'WRONG\' WHERE "{e["race_id"]}" = \'R2\' AND "{e["kettonum"]}" = \'H1\'',
            "duplicate_target": 'INSERT INTO outcomes SELECT * FROM outcomes LIMIT 1',
        }
        conn.execute(text(statements[fault]))
    with pytest.raises(NnInputContractError, match=message):
        port.load_training_inputs(input_query())


def test_large_integer_ids_and_missing_endpoints_keep_their_exact_identity(nn_engine):
    entries, history, targets = input_tables()
    race_ids = {"R0": 2026040101010101, "R1": 2026060101010101,
                "R2": 2026061301010101, "R3": 2026062001010101, "UNRELATED": 2026010101010101}
    # Include values above float64's consecutive-integer range.
    race_ids = {key: value * 10 + 1 for key, value in race_ids.items()}
    horse_ids = {"H1": 2023000001, "H2": 2023000002, "H3": 2023000003}
    with nn_engine.begin() as conn:
        for name, frame in zip(("entrants", "past_runs", "outcomes"), (entries, history, targets)):
            frame["race_id"] = pd.array([race_ids[value] for value in frame.race_id], dtype="Int64")
            frame["kettonum"] = pd.array([horse_ids[value] for value in frame.kettonum], dtype="Int64")
            if "last_history_race_id" in frame:
                frame["last_history_race_id"] = pd.array([race_ids.get(value) for value in frame.last_history_race_id], dtype="Int64")
            frame.to_sql(name, conn, index=False)
    port: NnInputRepositoryPort = SqlNnInputRepository(
        engine=nn_engine, mapping=NnInputMapping("entrants", "past_runs", "outcomes"), contract=feature_contract())
    result = port.load_training_inputs(input_query())
    assert result.inputs.entries.race_id.tolist() == ["20260613010101011", "20260613010101011", "20260620010101011"]
    assert result.inputs.entries.iloc[0].last_history_race_id == "20260601010101011"
    assert pd.isna(result.inputs.entries.iloc[1].last_history_race_id)
