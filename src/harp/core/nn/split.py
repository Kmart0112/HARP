"""Race-preserving temporal splits and complete-label admission."""
from dataclasses import dataclass
from datetime import date

from .contracts import NnInputContractError, NnTrainingInputs


@dataclass(frozen=True)
class NnDatasetConfig:
    train_end_date: str
    validation_end_date: str
    history_length: int = 10

    def __post_init__(self):
        try:
            train_end = date.fromisoformat(self.train_end_date)
            validation_end = date.fromisoformat(self.validation_end_date)
            if train_end >= validation_end:
                raise ValueError
        except (ValueError, TypeError) as exc:
            raise NnInputContractError("train end must precede validation end (ISO dates)") from exc
        object.__setattr__(self, "train_end_date", train_end.isoformat())
        object.__setattr__(self, "validation_end_date", validation_end.isoformat())
        if type(self.history_length) is not int or self.history_length < 1:
            raise NnInputContractError("history_length must be a positive integer")


@dataclass(frozen=True)
class NnRacePartition:
    race_id: str
    held_date: str
    split: str
    entrant_count: int
    exclusion_reason: str | None


def partition_nn_races(inputs: NnTrainingInputs, config: NnDatasetConfig) -> tuple[NnRacePartition, ...]:
    entries = inputs.inputs.entries
    entries["label_known"] = inputs.targets.is_place.notna().to_numpy()
    result = []
    for race_id, race in entries.groupby("race_id", sort=False):
        day = race.held_date.iloc[0].date().isoformat()
        split = "train" if day <= config.train_end_date else (
            "validation" if day <= config.validation_end_date else "test")
        result.append(NnRacePartition(
            race_id, day, split, len(race),
            None if race.label_known.all() else "missing_place_label",
        ))
    return tuple(result)
