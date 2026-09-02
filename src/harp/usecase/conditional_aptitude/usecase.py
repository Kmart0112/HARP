from __future__ import annotations

import pandas as pd

from harp.core.conditional_aptitude import (
    PairSpec,
    confirm_pair,
    prepare_pair_frame,
    screen_pair,
)

from .dto import (
    ConditionalAptitudeDeps,
    ConditionalAptitudeRequest,
    ConditionalAptitudeResult,
)


def run_conditional_aptitude_usecase(
    req: ConditionalAptitudeRequest,
    deps: ConditionalAptitudeDeps,
) -> ConditionalAptitudeResult:
    dates = _validate_request(req)
    pairs = _resolve_pairs(req)
    observations = deps.observation_repository.load_observations(
        columns=_required_observation_columns(req),
        from_date=dates["from_date"],
        to_date=dates["to_date"],
        filters=req.filters,
    )
    probabilities = deps.probability_provider.load_base_probabilities(
        key_cols=req.schema.key_cols,
        probability_col=req.schema.base_probability_col,
        from_date=dates["from_date"],
        to_date=dates["to_date"],
    )
    source = _merge_sources(observations, probabilities, req=req)

    entity_by_key = {entity.key: entity for entity in req.entities}
    condition_by_key = {condition.key: condition for condition in req.conditions}
    pair_by_id = {pair.pair_id: pair for pair in pairs}
    screen_results = []
    skipped_rows: list[dict[str, object]] = []
    for pair in pairs:
        prepared = prepare_pair_frame(
            source,
            entity=entity_by_key[pair.entity_key],
            condition=condition_by_key[pair.condition_key],
            schema=req.schema,
        )
        discovery = prepared.loc[
            (prepared["date"] >= dates["from_date"])
            & (prepared["date"] < dates["discovery_end"])
        ]
        screening = prepared.loc[
            (prepared["date"] >= dates["discovery_end"])
            & (prepared["date"] < dates["confirmation_start"])
        ]
        n_cells = int(discovery["entity_id"].nunique()) * int(
            discovery["condition_id"].nunique()
        )
        if discovery.empty or screening.empty or n_cells > req.screening_policy.max_cells:
            reason = "empty_window" if discovery.empty or screening.empty else "max_cells"
            skipped_rows.append(
                {
                    "pair_id": pair.pair_id,
                    "status": "skipped",
                    "skip_reason": reason,
                    "discovery_n": len(discovery),
                    "screening_n": len(screening),
                    "n_cells": n_cells,
                    "selected": False,
                }
            )
            continue
        screen_results.append(
            screen_pair(
                discovery,
                screening,
                pair_id=pair.pair_id,
                entity=entity_by_key[pair.entity_key],
                policy=req.screening_policy,
            )
        )

    selected_pair_ids = _select_pairs(screen_results, top_k=req.screening_policy.top_k)
    scan_rows = [result.summary for result in screen_results]
    for row in scan_rows:
        row["selected"] = row["pair_id"] in selected_pair_ids
    scan_summary = pd.DataFrame([*scan_rows, *skipped_rows])
    scan_cell_effects = _concat_or_empty(
        [result.cell_effects for result in screen_results]
    )

    screen_by_pair = {result.summary["pair_id"]: result for result in screen_results}
    confirmation_results = []
    for pair_id in selected_pair_ids:
        pair = pair_by_id[pair_id]
        prepared = prepare_pair_frame(
            source,
            entity=entity_by_key[pair.entity_key],
            condition=condition_by_key[pair.condition_key],
            schema=req.schema,
        )
        analysis_frame = prepared.loc[
            (prepared["date"] >= dates["from_date"])
            & (prepared["date"] < dates["to_date"])
        ].reset_index(drop=True)
        screen_result = screen_by_pair[pair_id]
        confirmation_results.append(
            confirm_pair(
                analysis_frame,
                pair_id=pair_id,
                validation_start=dates["confirmation_start"],
                validation_end=dates["to_date"],
                practical_interaction_rms=float(
                    screen_result.summary["interaction_rms_probability"]
                ),
                policy=req.confirmation_policy,
            )
        )

    return ConditionalAptitudeResult(
        analysis_id=req.analysis_id,
        selected_pair_ids=selected_pair_ids,
        scan_summary=scan_summary,
        scan_cell_effects=scan_cell_effects,
        confirmation_summary=pd.DataFrame(
            [result.summary for result in confirmation_results]
        ),
        fold_metrics=_concat_or_empty(
            [result.fold_metrics for result in confirmation_results]
        ),
        oos_predictions=_concat_or_empty(
            [result.oos_predictions for result in confirmation_results]
        ),
        confirmation_cell_stability=_concat_or_empty(
            [result.cell_stability for result in confirmation_results]
        ),
    )


def _validate_request(req: ConditionalAptitudeRequest) -> dict[str, pd.Timestamp]:
    if not req.analysis_id.strip():
        raise ValueError("analysis_id must not be empty")
    req.schema.validate()
    req.screening_policy.validate()
    req.confirmation_policy.validate()
    if not req.entities or not req.conditions:
        raise ValueError("at least one entity and condition spec are required")
    for entity in req.entities:
        entity.validate()
    for condition in req.conditions:
        condition.validate()
    entity_keys = [entity.key for entity in req.entities]
    condition_keys = [condition.key for condition in req.conditions]
    if len(entity_keys) != len(set(entity_keys)):
        raise ValueError("entity keys must be unique")
    if len(condition_keys) != len(set(condition_keys)):
        raise ValueError("condition keys must be unique")

    dates = {
        "from_date": pd.Timestamp(req.from_date).tz_localize(None),
        "discovery_end": pd.Timestamp(req.discovery_end).tz_localize(None),
        "confirmation_start": pd.Timestamp(req.confirmation_start).tz_localize(None),
        "to_date": pd.Timestamp(req.to_date).tz_localize(None),
    }
    if not (
        dates["from_date"]
        < dates["discovery_end"]
        < dates["confirmation_start"]
        < dates["to_date"]
    ):
        raise ValueError(
            "dates must satisfy from_date < discovery_end < confirmation_start < to_date"
        )
    return dates


def _resolve_pairs(req: ConditionalAptitudeRequest) -> tuple[PairSpec, ...]:
    if req.pairs:
        pairs = req.pairs
    else:
        pairs = tuple(
            PairSpec(
                pair_id=f"{entity.key}__{condition.key}",
                entity_key=entity.key,
                condition_key=condition.key,
            )
            for entity in req.entities
            for condition in req.conditions
        )
    entity_keys = {entity.key for entity in req.entities}
    condition_keys = {condition.key for condition in req.conditions}
    for pair in pairs:
        pair.validate()
        if pair.entity_key not in entity_keys:
            raise ValueError(f"unknown entity_key in pair {pair.pair_id}: {pair.entity_key}")
        if pair.condition_key not in condition_keys:
            raise ValueError(
                f"unknown condition_key in pair {pair.pair_id}: {pair.condition_key}"
            )
    pair_ids = [pair.pair_id for pair in pairs]
    if len(pair_ids) != len(set(pair_ids)):
        raise ValueError("pair_id values must be unique")
    return pairs


def _required_observation_columns(req: ConditionalAptitudeRequest) -> tuple[str, ...]:
    columns = [
        *req.schema.key_cols,
        req.schema.race_id_col,
        req.schema.date_col,
        req.schema.outcome_col,
    ]
    for entity in req.entities:
        columns.append(entity.id_col)
        if entity.label_col is not None:
            columns.append(entity.label_col)
    for condition in req.conditions:
        columns.extend(condition.source_cols)
    return tuple(dict.fromkeys(columns))


def _merge_sources(
    observations: pd.DataFrame,
    probabilities: pd.DataFrame,
    *,
    req: ConditionalAptitudeRequest,
) -> pd.DataFrame:
    probability_col = req.schema.base_probability_col
    if probability_col in observations.columns:
        raise ValueError(
            f"observation source must not contain provider-owned column: {probability_col}"
        )
    expected_probability_columns = {*req.schema.key_cols, probability_col}
    missing_probability_columns = expected_probability_columns.difference(
        probabilities.columns
    )
    if missing_probability_columns:
        raise KeyError(
            f"base probability columns are missing: {sorted(missing_probability_columns)}"
        )
    if observations.duplicated(list(req.schema.key_cols)).any():
        raise ValueError("observation keys must be unique")
    if probabilities.duplicated(list(req.schema.key_cols)).any():
        raise ValueError("base probability keys must be unique")
    source = observations.merge(
        probabilities[[*req.schema.key_cols, probability_col]],
        on=list(req.schema.key_cols),
        how="left",
        validate="one_to_one",
    )
    if source[probability_col].isna().any():
        missing_count = int(source[probability_col].isna().sum())
        raise ValueError(f"base probabilities are missing for {missing_count} observations")
    return source


def _select_pairs(screen_results: list, *, top_k: int) -> tuple[str, ...]:
    eligible = [result.summary for result in screen_results if result.summary["status"] == "eligible"]
    ranked = sorted(
        eligible,
        key=lambda row: (
            float(row["screen_delta_logloss"]),
            -float(row["interaction_rms_probability"]),
            -int(row["reliable_cell_count"]),
            str(row["pair_id"]),
        ),
    )
    return tuple(str(row["pair_id"]) for row in ranked[:top_k])


def _concat_or_empty(frames: list[pd.DataFrame]) -> pd.DataFrame:
    non_empty = [frame for frame in frames if not frame.empty]
    if not non_empty:
        return pd.DataFrame()
    return pd.concat(non_empty, ignore_index=True)
