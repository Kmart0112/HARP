from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ConditionTransformKind = Literal[
    "identity_category",
    "fixed_ranges",
    "cross_category",
    "cross_fixed_ranges",
]


@dataclass(frozen=True)
class NumericRange:
    label: str
    lower: float | None = None
    upper: float | None = None

    def validate(self) -> None:
        if not self.label.strip():
            raise ValueError("numeric range label must not be empty")
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError(f"numeric range lower must be <= upper: {self.label}")


@dataclass(frozen=True)
class EntitySpec:
    key: str
    id_col: str
    label_col: str | None = None
    min_total_n: int = 100
    min_condition_levels: int = 2

    def validate(self) -> None:
        if not self.key.strip():
            raise ValueError("entity key must not be empty")
        if not self.id_col.strip():
            raise ValueError(f"entity id_col must not be empty: {self.key}")
        if self.min_total_n < 1:
            raise ValueError(f"entity min_total_n must be >= 1: {self.key}")
        if self.min_condition_levels < 2:
            raise ValueError(f"entity min_condition_levels must be >= 2: {self.key}")


@dataclass(frozen=True)
class ConditionSpec:
    key: str
    source_cols: tuple[str, ...]
    transform: ConditionTransformKind = "identity_category"
    ranges: tuple[NumericRange, ...] = ()
    separator: str = " | "

    def validate(self) -> None:
        if not self.key.strip():
            raise ValueError("condition key must not be empty")
        if not self.source_cols or any(not col.strip() for col in self.source_cols):
            raise ValueError(f"condition source_cols must not be empty: {self.key}")
        if self.transform in {"identity_category", "fixed_ranges"} and len(self.source_cols) != 1:
            raise ValueError(
                f"{self.transform} requires exactly one source column: {self.key}"
            )
        if self.transform == "cross_category" and len(self.source_cols) < 2:
            raise ValueError(f"cross_category requires at least two source columns: {self.key}")
        if self.transform == "cross_fixed_ranges" and len(self.source_cols) < 2:
            raise ValueError(
                f"cross_fixed_ranges requires categorical columns plus one numeric column: {self.key}"
            )
        if self.transform in {"fixed_ranges", "cross_fixed_ranges"}:
            if not self.ranges:
                raise ValueError(f"ranges are required for {self.transform}: {self.key}")
            for numeric_range in self.ranges:
                numeric_range.validate()
            _validate_non_overlapping_ranges(self.ranges, condition_key=self.key)
        elif self.ranges:
            raise ValueError(f"ranges are only valid for fixed-range transforms: {self.key}")
        if not self.separator:
            raise ValueError(f"condition separator must not be empty: {self.key}")


@dataclass(frozen=True)
class PairSpec:
    pair_id: str
    entity_key: str
    condition_key: str

    def validate(self) -> None:
        if not self.pair_id.strip():
            raise ValueError("pair_id must not be empty")
        if not self.entity_key.strip():
            raise ValueError(f"entity_key must not be empty: {self.pair_id}")
        if not self.condition_key.strip():
            raise ValueError(f"condition_key must not be empty: {self.pair_id}")


@dataclass(frozen=True)
class ObservationSchema:
    key_cols: tuple[str, ...]
    race_id_col: str
    date_col: str
    outcome_col: str
    base_probability_col: str = "base_probability"

    def validate(self) -> None:
        values = (*self.key_cols, self.race_id_col, self.date_col, self.outcome_col)
        if not self.key_cols or any(not value.strip() for value in values):
            raise ValueError("observation schema columns must not be empty")
        if len(set(self.key_cols)) != len(self.key_cols):
            raise ValueError("observation key_cols must be unique")
        if not self.base_probability_col.strip():
            raise ValueError("base_probability_col must not be empty")


@dataclass(frozen=True)
class ScreeningPolicy:
    min_cell_n_for_claim: int = 20
    min_eligible_coverage: float = 0.70
    max_cells: int = 5_000
    practical_delta_probability: float = 0.01
    local_probability_threshold: float = 0.95
    main_penalty: float = 1.0
    top_k: int = 5

    def validate(self) -> None:
        if self.min_cell_n_for_claim < 1:
            raise ValueError("min_cell_n_for_claim must be >= 1")
        if not 0.0 <= self.min_eligible_coverage <= 1.0:
            raise ValueError("min_eligible_coverage must be in [0, 1]")
        if self.max_cells < 1:
            raise ValueError("max_cells must be >= 1")
        if not 0.0 < self.practical_delta_probability < 0.5:
            raise ValueError("practical_delta_probability must be in (0, 0.5)")
        if not 0.5 < self.local_probability_threshold < 1.0:
            raise ValueError("local_probability_threshold must be in (0.5, 1)")
        if self.main_penalty <= 0.0:
            raise ValueError("main_penalty must be > 0")
        if self.top_k < 1:
            raise ValueError("top_k must be >= 1")


@dataclass(frozen=True)
class ConfirmationPolicy:
    validation_months: int = 6
    step_months: int = 6
    tuning_months: int = 6
    min_folds: int = 2
    min_bootstrap_blocks: int = 8
    main_penalty: float = 1.0
    interaction_penalty_grid: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0)
    bootstrap_repetitions: int = 1_000
    practical_delta_probability: float = 0.01
    min_fold_win_rate: float = 0.75
    confidence_level: float = 0.95
    random_seed: int = 42

    def validate(self) -> None:
        if self.validation_months < 1 or self.step_months < 1 or self.tuning_months < 1:
            raise ValueError("confirmation month widths must be >= 1")
        if self.step_months < self.validation_months:
            raise ValueError(
                "step_months must be >= validation_months to avoid duplicate OOS rows"
            )
        if self.min_folds < 2:
            raise ValueError("min_folds must be >= 2")
        if self.min_bootstrap_blocks < 2:
            raise ValueError("min_bootstrap_blocks must be >= 2")
        if self.main_penalty <= 0.0:
            raise ValueError("main_penalty must be > 0")
        if not self.interaction_penalty_grid or any(
            penalty <= 0.0 for penalty in self.interaction_penalty_grid
        ):
            raise ValueError("interaction_penalty_grid must contain positive values")
        if self.bootstrap_repetitions < 100:
            raise ValueError("bootstrap_repetitions must be >= 100")
        if not 0.0 < self.practical_delta_probability < 0.5:
            raise ValueError("practical_delta_probability must be in (0, 0.5)")
        if not 0.5 <= self.min_fold_win_rate <= 1.0:
            raise ValueError("min_fold_win_rate must be in [0.5, 1]")
        if not 0.5 < self.confidence_level < 1.0:
            raise ValueError("confidence_level must be in (0.5, 1)")


def _validate_non_overlapping_ranges(
    ranges: tuple[NumericRange, ...],
    *,
    condition_key: str,
) -> None:
    labels = [numeric_range.label for numeric_range in ranges]
    if len(labels) != len(set(labels)):
        raise ValueError(f"numeric range labels must be unique: {condition_key}")

    def lower_value(value: float | None) -> float:
        return float("-inf") if value is None else float(value)

    def upper_value(value: float | None) -> float:
        return float("inf") if value is None else float(value)

    ordered = sorted(ranges, key=lambda numeric_range: lower_value(numeric_range.lower))
    previous_upper: float | None = None
    for numeric_range in ordered:
        lower = lower_value(numeric_range.lower)
        upper = upper_value(numeric_range.upper)
        if previous_upper is not None and lower <= previous_upper:
            raise ValueError(f"numeric ranges must not overlap: {condition_key}")
        previous_upper = upper
