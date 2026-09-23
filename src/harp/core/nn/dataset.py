"""Map-style race Dataset with shared histories and NumPy batches.

No tensor framework is needed to prepare/replay data. A later trainer can convert
the numeric arrays to its tensors. IDs remain separate alignment metadata.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .contracts import NnInputContractError, NnRaceInputs, NnTrainingInputs
from .preprocessing import (
    NnPreprocessingState, fit_table_preprocessor, nn_feature_fields,
    validate_preprocessing_schema,
)
from .split import NnDatasetConfig, NnRacePartition, partition_nn_races


# Deterministic relative encodings, independent of the fitted training statistics.
HISTORY_RELATIVE_NAMES = ("log1p_days_before_target", "runs_before_target_over_k")


class _HistoryIndex:
    def __init__(self, history: pd.DataFrame):
        first = ~history.kettonum.duplicated()
        self.offsets = dict(zip(history.loc[first, "kettonum"], np.flatnonzero(first), strict=True))

    def window(self, horse: str, end: int, length: int) -> slice:
        if end == 0:
            return slice(0, 0)
        offset = self.offsets[horse]
        return slice(offset + max(0, end - length), offset + end)


class NnRaceDataset:
    """One complete field per sample; slicing never expands the stored history bank.

    History is right padded, oldest to newest within valid slots. __getitem__
    returns independent arrays, so modifying a sample cannot alter later reads.
    """

    def __init__(self, inputs: NnRaceInputs | NnTrainingInputs,
                 preprocessing: NnPreprocessingState, history_length: int):
        if type(history_length) is not int or history_length < 1:
            raise NnInputContractError("history_length must be a positive integer")
        base = inputs.inputs if isinstance(inputs, NnTrainingInputs) else inputs
        validate_preprocessing_schema(base, preprocessing)
        entries, history = base.entries, base.history
        self._current = preprocessing.current.transform(entries)
        self._past = preprocessing.history.transform(history)
        self._history_index = _HistoryIndex(history)
        self._history_days = history.held_date.to_numpy(dtype="datetime64[D]")
        self._horse_ids = entries.kettonum.to_numpy()
        self._horse_numbers = entries.horse_number.to_numpy(dtype=np.int64)
        self._ends = entries.history_end_no.to_numpy(dtype=np.int64)
        self._dates = entries.held_date.to_numpy(dtype="datetime64[D]")
        self._race_rows = entries.groupby("race_id", sort=False).indices
        self._race_ids = tuple(self._race_rows)
        self._history_length = history_length
        labels = inputs.targets.is_place if isinstance(inputs, NnTrainingInputs) else pd.Series(pd.NA, index=entries.index, dtype="boolean")
        self._labels = labels.fillna(False).to_numpy(dtype=np.float32)
        self._label_mask = labels.notna().to_numpy(dtype=bool)
        self._preprocessing = preprocessing

    @property
    def preprocessing(self) -> NnPreprocessingState:
        return self._preprocessing

    @property
    def race_ids(self) -> tuple[str, ...]:
        return self._race_ids

    @property
    def history_length(self) -> int:
        return self._history_length

    def __len__(self) -> int:
        return len(self._race_ids)

    def __getitem__(self, index: int) -> dict:
        race_id = self._race_ids[index]
        rows = self._race_rows[race_id]
        size, length = len(rows), self.history_length
        sample = {
            "race_id": race_id,
            "horse_ids": tuple(self._horse_ids[rows]),
            "horse_numbers": self._horse_numbers[rows].copy(),
            "entrant_mask": np.ones(size, dtype=bool),
            "history_mask": np.zeros((size, length), dtype=bool),
            "history_relative": np.zeros((size, length, len(HISTORY_RELATIVE_NAMES)), dtype=np.float32),
            "labels": self._labels[rows].copy(),
            "label_mask": self._label_mask[rows].copy(),
        }
        for name, bank in self._current.items():
            sample[f"current_{name}"] = bank[rows].copy()
        for name, bank in self._past.items():
            sample[f"history_{name}"] = np.zeros((size, length, bank.shape[1]), dtype=bank.dtype)
        for position, row in enumerate(rows):
            window = self._history_index.window(self._horse_ids[row], self._ends[row], length)
            count = window.stop - window.start
            for name, bank in self._past.items():
                sample[f"history_{name}"][position, :count] = bank[window]
            sample["history_mask"][position, :count] = True
            days = (self._dates[row] - self._history_days[window]).astype(np.float64)
            sample["history_relative"][position, :count, 0] = np.log1p(days)
            sample["history_relative"][position, :count, 1] = np.arange(count - 1, -1, -1) / length
        return sample

    def select_races(self, race_ids: tuple[str, ...]) -> "NnRaceDataset":
        """Return a view sharing feature banks, preserving the requested race order."""
        if len(set(race_ids)) != len(race_ids) or not set(race_ids) <= set(self.race_ids):
            raise NnInputContractError("unknown or repeated race in Dataset selection")
        view = object.__new__(NnRaceDataset)
        view.__dict__ = self.__dict__.copy()
        view._race_ids = tuple(race_ids)
        return view


def collate_nn_races(samples: list[dict]) -> dict:
    """Pad horse dimension to the largest field in this batch; True means valid.

    Numeric/category columns remain separate for embeddings. Feature missingness,
    absent history, padded horses and unknown labels have independent masks.
    """
    if not samples:
        raise NnInputContractError("cannot collate an empty race batch")
    maximum = max(len(sample["horse_ids"]) for sample in samples)
    batch = {"race_ids": tuple(sample["race_id"] for sample in samples),
             "horse_ids": tuple(sample["horse_ids"] + (None,) * (maximum - len(sample["horse_ids"])) for sample in samples)}
    for name, value in samples[0].items():
        if not isinstance(value, np.ndarray):
            continue
        array = np.zeros((len(samples), maximum, *value.shape[1:]), dtype=value.dtype)
        for row, sample in enumerate(samples):
            other = sample[name]
            if other.shape[1:] != value.shape[1:] or other.dtype != value.dtype:
                raise NnInputContractError("race batch feature shapes or dtypes differ")
            array[row, :len(other)] = other
        batch[name] = array
    return batch


@dataclass(frozen=True)
class PreparedNnDataset:
    dataset: NnRaceDataset
    config: NnDatasetConfig
    partitions: tuple[NnRacePartition, ...]

    @property
    def preprocessing(self) -> NnPreprocessingState:
        return self.dataset.preprocessing

    def split(self, name: str) -> NnRaceDataset:
        if name not in {"train", "validation", "test"}:
            raise NnInputContractError("unknown NN split")
        return self.dataset.select_races(tuple(part.race_id for part in self.partitions
                                              if part.split == name and part.exclusion_reason is None))

    @property
    def summary(self) -> dict:
        return {name: {
            "races": sum(part.split == name and part.exclusion_reason is None for part in self.partitions),
            "entries": sum(part.entrant_count for part in self.partitions if part.split == name and part.exclusion_reason is None),
            "excluded_races": sum(part.split == name and part.exclusion_reason is not None for part in self.partitions),
            "excluded_entries": sum(part.entrant_count for part in self.partitions if part.split == name and part.exclusion_reason is not None),
        } for name in ("train", "validation", "test")}


def prepare_nn_dataset(inputs: NnTrainingInputs, config: NnDatasetConfig) -> PreparedNnDataset:
    partitions = partition_nn_races(inputs, config)
    train_ids = {part.race_id for part in partitions if part.split == "train" and part.exclusion_reason is None}
    if not train_ids:
        raise NnInputContractError("train split contains no fully labelled races")
    base = inputs.inputs
    entries, history = base.entries, base.history
    train = entries.loc[entries.race_id.isin(train_ids)]
    index = _HistoryIndex(history)
    eligible = np.zeros(len(history), dtype=bool)
    for row in train[["kettonum", "history_end_no"]].itertuples(index=False):
        eligible[index.window(row.kettonum, row.history_end_no, config.history_length)] = True
    current_fields, history_fields = nn_feature_fields(base)
    preprocessing = NnPreprocessingState(
        fit_table_preprocessor(train, current_fields),
        # Each reachable historical run contributes once, regardless of reuse.
        fit_table_preprocessor(history.loc[eligible], history_fields),
    )
    return PreparedNnDataset(NnRaceDataset(inputs, preprocessing, config.history_length), config, partitions)


def restore_nn_dataset(inputs: NnTrainingInputs, config: NnDatasetConfig,
                       preprocessing: NnPreprocessingState,
                       partitions: tuple[NnRacePartition, ...]) -> PreparedNnDataset:
    """Replay saved transforms and splits without fitting again."""
    if partition_nn_races(inputs, config) != partitions:
        raise NnInputContractError("saved splits differ from source inputs")
    if not any(part.split == "train" and part.exclusion_reason is None for part in partitions):
        raise NnInputContractError("saved Dataset has no training races")
    return PreparedNnDataset(NnRaceDataset(inputs, preprocessing, config.history_length), config, partitions)
