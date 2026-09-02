from __future__ import annotations

from typing import Any


def build_training_artifact_payload(
    *,
    model: Any,
    model_type: str,
    feature_names: list[str],
    cat_features: list[str],
    split_info: dict[str, int],
    metrics: dict[str, float | None],
    note: str,
    calibration_method: str,
    calibration_info: dict[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "model_type": model_type,
        "feature_names": feature_names,
        "cat_features": cat_features,
        "split_info": split_info,
        "metrics": metrics,
        "note": note,
    }
    if calibration_info is not None:
        payload["calibration"] = {
            "method": calibration_method,
            "params": calibration_info,
        }
    return payload
