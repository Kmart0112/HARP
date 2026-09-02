from __future__ import annotations

from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from harp.adapters.driven.storage import (
    LocalFileGatewayAdapter,
    load_dataframe_cache,
    save_dataframe_cache,
)
from harp.adapters.driven.tracking import MlflowTrackingAdapter


def test_local_storage_contract_round_trips_text_bytes_and_dataframes(tmp_path: Path) -> None:
    gateway = LocalFileGatewayAdapter()
    text_path = tmp_path / "nested" / "message.txt"
    copy_path = tmp_path / "copied" / "message.txt"
    bytes_path = tmp_path / "nested" / "payload.bin"

    gateway.write_text(str(text_path), "hello")
    gateway.write_bytes(str(bytes_path), b"payload")
    gateway.copy(str(text_path), str(copy_path))

    assert gateway.read_text(str(text_path)) == "hello"
    assert gateway.read_text(str(copy_path)) == "hello"
    assert gateway.read_bytes(str(bytes_path)) == b"payload"
    assert gateway.exists(str(copy_path)) is True

    frame = pd.DataFrame({"race_id": ["R1", "R2"], "value": [1.0, 2.0]})
    cache_path = tmp_path / "cache" / "features.parquet"
    save_dataframe_cache(frame, cache_path)
    assert_frame_equal(load_dataframe_cache(cache_path), frame)


def test_mlflow_tracking_contract_round_trips_parent_child_state_and_summary(tmp_path: Path) -> None:
    tracking = MlflowTrackingAdapter(tracking_uri=(tmp_path / "mlruns").resolve().as_uri())
    parent_run_id = tracking.start_run(
        "feature_validation",
        "theme",
        tags={"theme_status": "open"},
    )
    child_run_id = tracking.start_run(
        "feature_validation",
        "baseline_existing",
        parent_run_id=parent_run_id,
        tags={"scenario_name": "baseline_existing"},
    )

    tracking.log_params(child_run_id, {"feature_count": 2})
    tracking.log_metrics(child_run_id, {"auc": 0.72})
    tracking.log_dict(
        child_run_id,
        {"scenario_name": "baseline_existing", "decision": "基準"},
        "summary.json",
    )
    tracking.set_terminated(child_run_id, "FINISHED")
    tracking.set_terminated(parent_run_id, "FINISHED")

    child = tracking.get_run(child_run_id)
    assert child.status == "FINISHED"
    assert child.params["feature_count"] == "2"
    assert child.metrics["auc"] == 0.72
    assert [run.run_id for run in tracking.list_child_runs(parent_run_id)] == [child_run_id]
    assert tracking.read_dict_artifact(child_run_id, "summary.json") == {
        "scenario_name": "baseline_existing",
        "decision": "基準",
    }
