"""Race-preserving temporal splits and complete-label admission."""
from dataclasses import dataclass
from datetime import date

from .contracts import NnInputContractError, NnTrainingInputs
from .tasks import nn_target


@dataclass(frozen=True)
class NnDatasetConfig:
    train_end_date: str
    validation_end_date: str
    history_length: int = 10
    task: str = "place"

    def __post_init__(self):
        nn_target(self.task)
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
    targets = inputs.targets
    labels = targets[nn_target(config.task)]
    entries["label_known"] = labels.notna().to_numpy()
    entries["winner"] = labels.fillna(False).to_numpy(dtype=bool)
    entries["win_order_consistent"] = (
        targets.is_win.eq(targets.result_order.eq(1)) & targets.result_order.notna()
    ).fillna(False).to_numpy(dtype=bool)
    result = []
    for race_id, race in entries.groupby("race_id", sort=False):
        day = race.held_date.iloc[0].date().isoformat()
        split = "train" if day <= config.train_end_date else (
            "validation" if day <= config.validation_end_date else "test")
        reason = None
        if not race.label_known.all():
            reason = f"missing_{config.task}_label"
        elif config.task == "win":
            if not race.win_order_consistent.all():
                reason = "inconsistent_win_result"
            elif race.winner.sum() > 1:
                reason = "dead_heat"
            elif race.winner.sum() == 0:
                reason = "no_winner"
        result.append(NnRacePartition(race_id, day, split, len(race), reason))
    return tuple(result)
