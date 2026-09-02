from __future__ import annotations

from harp.adapters.driven import (
    CsvConditionSplitReportReaderAdapter,
    LocalFileGatewayAdapter,
    MlflowTrackingAdapter,
    TrackingConditionPublisherAdapter,
)
from harp.config import HarpRuntimeConfig
from harp.usecase import ConditionSplitCompareTrackingDeps


def build_condition_split_compare_tracking_deps(
    config: HarpRuntimeConfig,
) -> ConditionSplitCompareTrackingDeps:
    file_gateway = LocalFileGatewayAdapter()
    tracking = MlflowTrackingAdapter(tracking_uri=config.tracking.mlflow_tracking_uri)
    return ConditionSplitCompareTrackingDeps(
        report_reader=CsvConditionSplitReportReaderAdapter(file_gateway),
        publisher=TrackingConditionPublisherAdapter(tracking),
    )
