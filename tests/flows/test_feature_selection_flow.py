from __future__ import annotations

from dataclasses import replace
from unittest.mock import create_autospec

import yaml

from harp.core.feature_definitions import FeatureSetDefinition
from harp.interface.ports import (
    FeatureDefinitionPort,
    FeatureSelectionMetricsRunnerPort,
)
from harp.interface.ports.validation_runner_ports import MetricsRunResult
from harp.usecase import (
    FeatureSelectionDeps,
    FeatureSelectionReportSpec,
    FeatureSelectionRequest,
    VariantGroupSpec,
    run_feature_selection_usecase,
)
from tests.flow_support import (
    make_file_gateway_mock,
    make_parent_artifact_publisher_mock,
    make_tracking_port_mock,
)


def _metrics(name: str, *, auc: float, logloss: float) -> MetricsRunResult:
    return MetricsRunResult(
        scenario_name=name,
        timestamp="2026-08-10T00:00:00+09:00",
        auc=auc,
        logloss=logloss,
        brier=0.20,
        artifact_path=f"outputs/{name}.pkl",
        manifest_path=f"outputs/{name}.json",
        log_path=f"outputs/{name}.log",
    )


def _request() -> FeatureSelectionRequest:
    return FeatureSelectionRequest(
        validation_name="variant_selection",
        category="feature_selection",
        change_summary="select_variant",
        experiment_name="feature_selection",
        preset_name="variant_selection",
        feature_sets_path="contracts/features",
        target_contract_path="contracts/features/place/selected.yml",
        report_out="reports/feature_selection.md",
        runs_csv_out="reports/feature_selection_runs.csv",
        decisions_csv_out="reports/feature_selection_decisions.csv",
        selected_contract_snapshot_out="outputs/selected.yml",
        run_log_dir="outputs/feature_selection",
        command="run_feature_selection --preset variant_selection",
        git_commit="abc123",
        resume_parent_run_id=None,
        scenario_filter=(),
        finalize=False,
        append_note=None,
        write_contract=False,
        base_feature_set_name="place_v1",
        aggregate_groups=(),
        variant_groups=(
            VariantGroupSpec(
                group_id="pace_variant",
                candidates=("pace_current", "pace_new"),
            ),
        ),
        report_spec=FeatureSelectionReportSpec(
            title="Pace variant selection",
            background="Choose one implemented pace feature.",
            hypothesis_lines=("The new variant improves validation metrics.",),
            leakage_notes=("pre-race only",),
            implementation_notes=("one winner is promoted",),
        ),
    )


def _feature_definition_mock() -> FeatureDefinitionPort:
    definitions = create_autospec(FeatureDefinitionPort, instance=True, spec_set=True)
    definitions.load_feature_set.return_value = FeatureSetDefinition(
        name="place_v1",
        feature_names=("base_speed", "pace_current"),
        cat_features=(),
    )
    definitions.find_contract_path.return_value = "contracts/features/place/place_v1.yml"
    definitions.render_feature_config.side_effect = lambda *, feature_names, cat_features: yaml.safe_dump(
        {"feature_names": feature_names, "cat_features": cat_features},
        sort_keys=False,
    )
    definitions.render_contract.side_effect = (
        lambda *, contract_name, feature_names, cat_features: yaml.safe_dump(
            {
                "name": contract_name,
                "feature_names": feature_names,
                "cat_features": cat_features,
            },
            sort_keys=False,
        )
    )
    return definitions


def test_feature_selection_flow_compares_then_finalizes_the_winning_implemented_variant() -> None:
    files, file_state = make_file_gateway_mock(
        {
            "contracts/features/place/place_v1.yml": (
                "name: place_v1\nfeature_names: [base_speed, pace_current]\ncat_features: []\n"
            ),
        }
    )
    tracking, tracking_state = make_tracking_port_mock()
    metrics_runner = create_autospec(
        FeatureSelectionMetricsRunnerPort,
        instance=True,
        spec_set=True,
    )
    metrics_by_scenario = {
        "baseline_existing": _metrics("baseline_existing", auc=0.60, logloss=0.40),
        "variant__pace_variant__pace_current": _metrics(
            "variant__pace_variant__pace_current",
            auc=0.60,
            logloss=0.40,
        ),
        "variant__pace_variant__pace_new": _metrics(
            "variant__pace_variant__pace_new",
            auc=0.62,
            logloss=0.38,
        ),
    }
    metrics_runner.run_metrics.side_effect = (
        lambda **kwargs: metrics_by_scenario[str(kwargs["scenario_name"])]
    )
    publisher = make_parent_artifact_publisher_mock(file_gateway=files, tracking=tracking)
    deps = FeatureSelectionDeps(
        file_gateway=files,
        feature_definition_port=_feature_definition_mock(),
        tracking_port=tracking,
        parent_artifact_publisher=publisher,
        metrics_runner_port=metrics_runner,
    )

    started = run_feature_selection_usecase(_request(), deps)
    finalized = run_feature_selection_usecase(
        replace(
            _request(),
            resume_parent_run_id=started.parent_run_id,
            scenario_filter=("variant__pace_variant__pace_new",),
            finalize=True,
            append_note="final comparison",
            write_contract=True,
        ),
        deps,
    )

    assert started.theme_status == "open"
    assert started.theme_revision == 1
    assert started.contract_written is False
    assert finalized.parent_run_id == started.parent_run_id
    assert finalized.theme_status == "finalized"
    assert finalized.theme_revision == 2
    assert finalized.contract_written is True
    assert len(finalized.decisions) == 1
    assert finalized.decisions[0].winner_set == "pace_new"
    assert finalized.decisions[0].unresolved is False
    promoted_contract = file_state.files["contracts/features/place/selected.yml"]
    assert "pace_new" in promoted_contract
    assert "pace_current" not in promoted_contract
    assert "pace_new" in file_state.files["outputs/selected.yml"]
    assert tracking_state.runs[finalized.parent_run_id]["status"] == "FINISHED"
    assert tracking_state.runs[finalized.parent_run_id]["tags"]["theme_status"] == "finalized"
    assert publisher.publish_parent_artifacts.call_count == 2
