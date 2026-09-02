from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

import pandas as pd


class ConditionalAptitudeObservationRepositoryPort(Protocol):
    def load_observations(
        self,
        *,
        columns: Sequence[str],
        from_date: pd.Timestamp,
        to_date: pd.Timestamp,
        filters: Mapping[str, object],
    ) -> pd.DataFrame:
        ...


class ConditionalAptitudeProbabilityProviderPort(Protocol):
    def load_base_probabilities(
        self,
        *,
        key_cols: Sequence[str],
        probability_col: str,
        from_date: pd.Timestamp,
        to_date: pd.Timestamp,
    ) -> pd.DataFrame:
        ...
