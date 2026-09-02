from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import pandas as pd

from harp.core.conditional_aptitude import (
    ConditionSpec,
    ConfirmationPolicy,
    EntitySpec,
    ObservationSchema,
    PairSpec,
    ScreeningPolicy,
)
from harp.interface.ports import (
    ConditionalAptitudeObservationRepositoryPort,
    ConditionalAptitudeProbabilityProviderPort,
)


@dataclass(frozen=True)
class ConditionalAptitudeRequest:
    analysis_id: str
    from_date: str | pd.Timestamp
    discovery_end: str | pd.Timestamp
    confirmation_start: str | pd.Timestamp
    to_date: str | pd.Timestamp
    schema: ObservationSchema
    entities: tuple[EntitySpec, ...]
    conditions: tuple[ConditionSpec, ...]
    pairs: tuple[PairSpec, ...] = ()
    screening_policy: ScreeningPolicy = field(default_factory=ScreeningPolicy)
    confirmation_policy: ConfirmationPolicy = field(default_factory=ConfirmationPolicy)
    filters: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ConditionalAptitudeDeps:
    observation_repository: ConditionalAptitudeObservationRepositoryPort
    probability_provider: ConditionalAptitudeProbabilityProviderPort


@dataclass(frozen=True)
class ConditionalAptitudeResult:
    analysis_id: str
    selected_pair_ids: tuple[str, ...]
    scan_summary: pd.DataFrame
    scan_cell_effects: pd.DataFrame
    confirmation_summary: pd.DataFrame
    fold_metrics: pd.DataFrame
    oos_predictions: pd.DataFrame
    confirmation_cell_stability: pd.DataFrame
