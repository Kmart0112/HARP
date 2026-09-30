import os
from uuid import uuid4

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from harp.adapters.driven.db.final_odds_repository import (
    FinalOddsMapping,
    SqlFinalPlaceOddsRepository,
)
from harp.adapters.driven.storage.nn_odds_snapshot_store import (
    ParquetNnOddsSnapshotStore,
)
from harp.core.nn.odds_targets import FinalPlaceOddsQuery
from harp.interface.ports.nn_odds_ports import (
    FinalPlaceOddsRepositoryPort,
    NnOddsSnapshotStorePort,
)
from tests.nn_odds_support import snapshot


@pytest.fixture(params=["sqlite"] + (["postgres"] if os.environ.get("HARP_CONTRACT_TEST_DB_URL") else []))
def odds_engine(request):
    if request.param == "sqlite":
        engine = create_engine("sqlite://")
        yield engine
        engine.dispose()
        return
    admin = create_engine(os.environ["HARP_CONTRACT_TEST_DB_URL"])
    schema = "harp_final_odds_test_" + uuid4().hex
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(os.environ["HARP_CONTRACT_TEST_DB_URL"], connect_args={"options": f"-c search_path={schema}"})
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture(params=["original", "renamed", "extra", "text_values"])
def final_provider(request, odds_engine):
    # Race IDs exceed float64's consecutive integer range.
    table = pd.DataFrame({"race_id": [20250101010101011, 20250101010101011], "horse_number": [1, 2],
                          "odds_fukusho_low": [1.2, None], "odds_fukusho_high": [2.4, 3.5],
                          "updated_at": [pd.Timestamp("2026-09-25T00:00:00Z")] * 2})
    if request.param == "text_values":
        table["race_id"] = table.race_id.astype(str)
        for name in ("odds_fukusho_low", "odds_fukusho_high"):
            table[name] = table[name].map(lambda value: None if pd.isna(value) else str(value))
    original = FinalOddsMapping().columns
    names = {name: f"column_{i}" if request.param == "renamed" else name for i, name in enumerate(table)}
    columns = {logical: names[physical] for logical, physical in original.items()}
    stage_columns = {key: value for key, value in columns.items() if key != "source_updated_at"}
    if request.param == "extra":
        table["unused"] = "does not affect teachers"
        names["unused"] = "unused"
    with odds_engine.begin() as c:
        table.rename(columns=names).to_sql("final_quotes", c, index=False)
        table.drop(columns="updated_at").rename(columns=names).to_sql("staging_quotes", c, index=False)
    mapping = FinalOddsMapping(table="final_quotes", columns=columns,
                               staging_table="staging_quotes", staging_columns=stage_columns,
                               race_id_type="text" if request.param == "text_values" else "bigint",
                               source_timezone="UTC")
    port: FinalPlaceOddsRepositoryPort = SqlFinalPlaceOddsRepository(engine=odds_engine, mapping=mapping, batch_size=1)
    return port, odds_engine, mapping


def requested():
    return FinalPlaceOddsQuery(pd.DataFrame({"race_id": ["20250101010101011"] * 3, "horse_number": [3, 2, 1]}))


def test_final_odds_port_preserves_exact_keys_values_missing_rows_and_provenance(final_provider):
    port, _, _ = final_provider
    result = port.load(requested())
    frame = result.frame
    assert frame.race_id.tolist() == ["20250101010101011"] * 3
    assert frame.source_found.tolist() == [True, True, False]
    assert frame.loc[0, ["place_low", "place_high"]].tolist() == [1.2, 2.4]
    assert pd.isna(frame.loc[1, "place_low"]) and frame.loc[1, "place_high"] == 3.5
    assert frame.loc[2, ["place_low", "place_high", "source_updated_at"]].isna().all()
    assert frame.source_updated_at.iloc[0] == pd.Timestamp("2026-09-25T00:00:00Z")
    assert result.source["kind"] == "final" and result.source["staging_checked"]


@pytest.mark.parametrize("fault", ["duplicate_final", "hidden_staging_duplicate", "stale_final", "missing_column", "absent_table"])
def test_source_integrity_failures_are_not_silently_replaced_by_missing_odds(final_provider, fault):
    port, engine, mapping = final_provider
    price = mapping.columns["place_low"]
    with engine.begin() as c:
        if fault == "duplicate_final":
            c.execute(text("INSERT INTO final_quotes SELECT * FROM final_quotes LIMIT 1"))
        elif fault == "hidden_staging_duplicate":
            c.execute(text("INSERT INTO staging_quotes SELECT * FROM staging_quotes LIMIT 1"))
        elif fault == "stale_final":
            c.execute(text(f'UPDATE final_quotes SET "{price}" = 5'))
        elif fault == "missing_column":
            c.execute(text(f'ALTER TABLE final_quotes RENAME COLUMN "{price}" TO unexpected'))
        else:
            c.execute(text("DROP TABLE final_quotes"))
    with pytest.raises(ValueError, match="duplicate|differ from staging|schema"):
        port.load(requested())


def test_final_odds_snapshot_round_trip_needs_no_repository_and_preserves_invalid_values(tmp_path):
    store: NnOddsSnapshotStorePort = ParquetNnOddsSnapshotStore(tmp_path)
    value = snapshot()
    identity = store.save(value)
    restored = store.load(identity)
    pd.testing.assert_frame_equal(restored.frame, value.frame)
    pd.testing.assert_frame_equal(restored.coverage, value.coverage)
    assert restored.entry_keys_sha256 == value.entry_keys_sha256
    assert restored.prepared_dataset_id == "a" * 64
    assert store.save(value) == identity
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.parametrize("filename", ["odds.parquet", "coverage.csv", "manifest.json"])
def test_corrupt_teacher_artifacts_are_rejected_before_replay(tmp_path, filename):
    store = ParquetNnOddsSnapshotStore(tmp_path)
    identity = store.save(snapshot())
    with (tmp_path / identity / filename).open("ab") as stream:
        stream.write(b"corruption")
    with pytest.raises(ValueError, match="integrity"):
        store.load(identity)
