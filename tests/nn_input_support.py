"""Small longitudinal race examples, shared by public contract tests."""
from datetime import UTC, datetime

import pandas as pd

from harp.core.nn.contracts import NnFeatureContract, NnFeatureField, NnInputQuery, NnRaceInputs, NnTrainingInputs


def feature_contract():
    return NnFeatureContract(
        (NnFeatureField("age", "numeric"), NnFeatureField("sex_cd", "categorical"),
         NnFeatureField("jockey_place_rate_3y_smooth", "numeric")),
        (NnFeatureField("result_order", "numeric"), NnFeatureField("result_status_code", "categorical")),
    )


def input_query(**kwargs):
    values = dict(from_date="2026-06-13", to_date="2026-06-20",
                  feature_names=("age", "sex_cd", "jockey_place_rate_3y_smooth"),
                  history_result_names=("result_order", "result_status_code"))
    return NnInputQuery(**(values | kwargs))


def input_tables():
    def pre(race, horse, day, rate):
        return dict(race_id=race, kettonum=horse, held_date=day, age=3, sex_cd="1",
                    jockey_place_rate_3y_smooth=rate,
                    monthly_stats_cutoff=day[:7] + "-01", yearly_stats_cutoff=day[:4] + "-01-01",
                    jockey_stats_missing=rate is None, trainer_stats_missing=True,
                    breeder_stats_missing=True, sire_stats_missing=True,
                    dam_stats_missing=True, damsire_stats_missing=True)
    entries = pd.DataFrame([
        pre("R2", "H1", "2026-06-13", .30) | dict(horse_number=1, history_end_no=2,
            last_history_race_id="R1", last_history_held_date="2026-06-01", days_since_last_run=12, active_entrant_count=2),
        pre("R2", "H2", "2026-06-13", None) | dict(horse_number=2, history_end_no=0,
            last_history_race_id=None, last_history_held_date=None, days_since_last_run=None, active_entrant_count=2),
        pre("R3", "H1", "2026-06-20", .35) | dict(horse_number=1, history_end_no=3,
            last_history_race_id="R2", last_history_held_date="2026-06-13", days_since_last_run=7, active_entrant_count=1),
    ])
    history = pd.DataFrame([
        pre("R0", "H1", "2026-04-01", .10) | dict(run_no=1, result_order=1, result_status_code=None),
        pre("R1", "H1", "2026-06-01", .20) | dict(run_no=2, result_order=None, result_status_code="4"),
        pre("R2", "H1", "2026-06-13", .30) | dict(run_no=3, result_order=2, result_status_code=None),
        pre("R3", "H1", "2026-06-20", .35) | dict(run_no=4, result_order=1, result_status_code=None),
        pre("UNRELATED", "H3", "2026-01-01", .50) | dict(run_no=1, result_order=3, result_status_code=None),
    ])
    targets = pd.DataFrame([
        dict(race_id="R2", kettonum="H1", result_order=2, is_win=0, is_place=1),
        dict(race_id="R3", kettonum="H1", result_order=1, is_win=1, is_place=1),
    ])
    return entries, history, targets


def training_inputs():
    entries, history, targets = input_tables()
    inputs = NnRaceInputs(entries, history.iloc[:3], query=input_query(), contract=feature_contract(),
                         source_revision="fixture-v1", captured_at=datetime(2026, 6, 21, tzinfo=UTC))
    targets = entries[["race_id", "kettonum"]].merge(targets, how="left", on=["race_id", "kettonum"])
    return NnTrainingInputs(inputs, targets)
