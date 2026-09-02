from __future__ import annotations

from enum import StrEnum
from typing import Self


class _TrainingValue(StrEnum):
    @classmethod
    def from_str(cls, value: str) -> Self:
        normalized = str(value).strip().lower()
        try:
            return cls(normalized)
        except ValueError as exc:
            candidates = ", ".join(item.value for item in cls)
            raise ValueError(f"Unknown {cls.__name__}: {value!r}. candidates={candidates}") from exc


class TaskKind(_TrainingValue):
    PLACE = "place"
    WIN = "win"


class ModelType(_TrainingValue):
    PLACE = "place"
    PLACE_PLATT = "place_platt"
    WIN = "win"


class CalibrationMethod(_TrainingValue):
    NONE = "none"
    PLATT_LOGODDS = "platt_logodds"

    @classmethod
    def from_str(cls, value: str) -> Self:
        try:
            return cls(str(value).strip().lower())
        except ValueError as exc:
            candidates = ", ".join(method.value for method in cls)
            raise ValueError(f"Unknown calibration method: {value!r}. candidates={candidates}") from exc
