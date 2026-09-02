from __future__ import annotations

from dataclasses import replace
from unittest.mock import create_autospec

import yaml

from harp.core.feature_definitions import FeatureSetDefinition
from harp.interface.ports import (
    FeatureDefinitionPort,
    FeatureValidationMetricsRunnerPort,
    FeatureValidationShapRunnerPort,
)
from harp.interface.ports.validation_runner_ports import (
    MetricsRunResult,
    ShapReviewResult,
)
from harp.usecase import (
    FeatureDefinitionSpec,
    FeatureToggleSpec,
    FeatureValidationDeps,
    FeatureValidationReportSpec,
    FeatureValidationRequest,
    ShapReviewSpec,
    ValidationScenarioSpec,
    run_feature_validation_usecase,
)
from tests.flow_support import (
    make_file_gateway_mock,
    make_parent_artifact_publisher_mock,
    make_tracking_port_mock,
)


def _request() -> FeatureValidationRequest:
    return FeatureValidationRequest(
        validation_name="raw_course_features",
        category="feature_engineering",
        change_summary="add_turn_direction",
        experiment_name="feature_validation",
        preset_name="raw_course_features",
        features_config_path="config/features.yml",
        feature_sets_path="contracts/features",
        report_out="reports/feature_validation.md",
        runs_csv_out="reports/feature_validation_runs.csv",
        run_log_dir="outputs/feature_validation",
        command="run_feature_validation --preset raw_course_features",
        git_commit="abc123",
        resume_parent_run_id=None,
        scenario_filter=(),
        finalize=False,
        final_selected_scenario=None,
        append_note=None,
        scenarios=(
            ValidationScenarioSpec(
                scenario_name="baseline_existing",
                toggles=(),
                validation_mode="baseline",
            ),
            ValidationScenarioSpec(
                scenario_name="add_turn_direction",
                toggles=(
                    FeatureToggleSpec(
                        "turn_direction",
                        ("feature_names", "cat_features"),
                        True,
                    ),
                ),
                validation_mode="single_add",
                shap_request=ShapReviewSpec(
                    candidate_feature="turn_direction",
                    comparison_features=(),
                    validation_mode="single_add",
                    report_run_label="turn_direction",
                ),
            ),
        ),
        report_spec=FeatureValidationReportSpec(
            title="Turn direction validation",
            background="Validate the new feature.",
            hypothesis_lines=("Turn direction improves place probability.",),
            target_features=(
                FeatureDefinitionSpec(
                    feature_name="turn_direction",
                    feature_type="cat",
                    change_type="add",
                    summary="turn direction",
                    sections=("feature_names", "cat_features"),
                ),
            ),
            leakage_notes=("pre-race only",),
            implementation_notes=("no source mutation",),
            metrics_notebook_path="metrics.py",
            shap_notebook_path="shap.py",
        ),
    )


def _metrics(name: str, *, auc: float, logloss: float, brier: float) -> MetricsRunResult:
    return MetricsRunResult(
        scenario_name=name,
        timestamp="2026-08-10T00:00:00+09:00",
        auc=auc,
        logloss=logloss,
        brier=brier,
        artifact_path=f"outputs/{name}.pkl",
        manifest_path=f"outputs/{name}.json",
        log_path=f"outputs/{name}.log",
    )


def _shap_result() -> ShapReviewResult:
    return ShapReviewResult(
        scenario_name="add_turn_direction",
        candidate_feature="turn_direction",
        metrics_judgement="improved",
        shap_judgement="問題なし",
        final_recommendation="adopt",
        official_report_path="reports/shap.md",
        official_report_source_path="outputs/shap.md",
        summary_json_path="outputs/shap-summary.json",
        manifest_json_path="outputs/shap-manifest.json",
        artifact_bundle_dir="outputs/shap",
        artifact_report_path="outputs/shap/full-report.md",
        candidate_dependence_path="",
        candidate_dependence_source_path="",
        global_rank="1",
        mean_abs_shap="0.12",
        importance_share="0.15",
        log_path="outputs/shap.log",
    )


def _feature_definition_mock() -> FeatureDefinitionPort:
    definitions = create_autospec(FeatureDefinitionPort, instance=True, spec_set=True)
    definitions.is_registry_path.return_value = False

    def parse_config(text: str, *, source: str) -> FeatureSetDefinition:
        del source
        document = yaml.safe_load(text)
        return FeatureSetDefinition(
            feature_names=tuple(document.get("feature_names") or ()),
            cat_features=tuple(document.get("cat_features") or ()),
        )

    definitions.parse_feature_config_text.side_effect = parse_config
    return definitions


def test_feature_validation_flow_runs_start_append_and_finalize_with_the_same_mocked_ports() -> None:
    source_config = (
        "feature_names:\n"
        "- base_speed\n"
        "# - turn_direction\n"
        "cat_features:\n"
        "# - turn_direction\n"
    )
    files, file_state = make_file_gateway_mock({"config/features.yml": source_config})
    tracking, tracking_state = make_tracking_port_mock()

    metrics_runner = create_autospec(
        FeatureValidationMetricsRunnerPort,
        instance=True,
        spec_set=True,
    )
    metrics_by_scenario = {
        "baseline_existing": _metrics(
            "baseline_existing",
            auc=0.60,
            logloss=0.40,
            brier=0.20,
        ),
        "add_turn_direction": _metrics(
            "add_turn_direction",
            auc=0.62,
            logloss=0.38,
            brier=0.18,
        ),
    }
    metrics_runner.run_metrics.side_effect = (
        lambda **kwargs: metrics_by_scenario[str(kwargs["scenario_name"])]
    )

    shap_runner = create_autospec(
        FeatureValidationShapRunnerPort,
        instance=True,
        spec_set=True,
    )
    shap_runner.run_shap_review.return_value = _shap_result()
    publisher = make_parent_artifact_publisher_mock(file_gateway=files, tracking=tracking)
    deps = FeatureValidationDeps(
        file_gateway=files,
        feature_definition_port=_feature_definition_mock(),
        tracking_port=tracking,
        parent_artifact_publisher=publisher,
        metrics_runner_port=metrics_runner,
        shap_runner_port=shap_runner,
    )

    started = run_feature_validation_usecase(_request(), deps)
    appended = run_feature_validation_usecase(
        replace(
            _request(),
            resume_parent_run_id=started.parent_run_id,
            scenario_filter=("add_turn_direction",),
            append_note="rerun candidate",
        ),
        deps,
    )
    finalized = run_feature_validation_usecase(
        replace(
            _request(),
            resume_parent_run_id=started.parent_run_id,
            finalize=True,
            append_note="close theme",
        ),
        deps,
    )

    assert started.theme_status == "open"
    assert started.theme_revision == 1
    assert appended.parent_run_id == started.parent_run_id
    assert appended.theme_status == "open"
    assert appended.theme_revision == 2
    assert finalized.parent_run_id == started.parent_run_id
    assert finalized.decision == "採用"
    assert finalized.theme_status == "finalized"
    assert finalized.theme_revision == 3
    assert finalized.restored_features_state is True
    assert [scenario.scenario_name for scenario in finalized.scenario_results] == [
        "baseline_existing",
        "add_turn_direction",
    ]
    assert finalized.scenario_results[1].enabled_features == ("base_speed", "turn_direction")
    assert finalized.scenario_results[1].enabled_cat_features == ("turn_direction",)
    assert file_state.files["config/features.yml"] == source_config
    assert "採用" in file_state.files["reports/feature_validation.md"]
    assert file_state.files["reports/feature_validation_runs.csv"].startswith("scenario,scenario_run_id")
    assert tracking_state.runs[finalized.parent_run_id]["status"] == "FINISHED"
    assert tracking_state.runs[finalized.parent_run_id]["tags"]["theme_status"] == "finalized"
    assert publisher.publish_parent_artifacts.call_count == 3
