from dataclasses import dataclass
from typing import Protocol

from harp.core.calibration import CalibrationReport
from harp.core.calibration_prediction import CalibrationPredictions


@dataclass(frozen=True)
class CalibrationSource:
    model: object
    dataset: object
    metadata: dict


class CalibrationSourcePort(Protocol):
    def load(self, model: str, dataset: str, *, checkpoint_id: str | None = None) -> CalibrationSource:
        """Restore frozen model/data with their identities, without fitting or DB access."""
        ...


class CalibrationReportPort(Protocol):
    def save(self, report: CalibrationReport, output_dir: str) -> dict[str, str]:
        """Publish a complete report into a new directory; never replace an existing report."""
        ...


class CalibrationPredictionsPort(Protocol):
    def load(self, report_dir: str) -> CalibrationPredictions:
        """Verify saved prediction bytes and restore their evaluation provenance."""
        ...
