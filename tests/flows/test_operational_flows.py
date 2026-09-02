from __future__ import annotations

from pathlib import Path
from unittest.mock import create_autospec

from harp.core.condition_tracking import ConditionSplitReport
from harp.core.feature_definitions import FeatureSetDefinition
from harp.interface.ports import (
    ConditionSplitReportReaderPort,
    ConditionTrackingPublisherPort,
    FeatureDefinitionPort,
    FileGatewayPort,
    MlflowStorePort,
    MlflowStoreVerification,
    TableParquetExportArtifact,
    TableParquetExportPort,
)
from harp.usecase.condition_tracking.dto import (
    ConditionSplitCompareTrackingDeps,
    ConditionSplitCompareTrackingRequest,
)
from harp.usecase.condition_tracking.usecase import (
    run_log_condition_split_compare_usecase,
)
from harp.usecase.feature_contract.dto import (
    ExportFeatureContractDeps,
    ExportFeatureContractRequest,
)
from harp.usecase.feature_contract.export import run_export_feature_contract_usecase
from harp.usecase.mlflow_store.dto import (
    MlflowStoreMigrationDeps,
    MlflowStoreMigrationRequest,
)
from harp.usecase.mlflow_store.migration import run_migrate_mlflow_store_usecase
from harp.usecase.table_export.dto import (
    ExportTableToParquetDeps,
    ExportTableToParquetRequest,
)
from harp.usecase.table_export.parquet import run_export_table_to_parquet_usecase


def test_feature_contract_flow_writes_the_resolved_feature_set() -> None:
    files = create_autospec(FileGatewayPort, instance=True, spec_set=True)
    files.exists.side_effect = lambda path: path == "registry.yml"

    definitions = create_autospec(FeatureDefinitionPort, instance=True, spec_set=True)
    definitions.load_feature_set.return_value = FeatureSetDefinition(
        name="place_v1",
        feature_names=("speed", "course"),
        cat_features=("course",),
    )
    definitions.render_contract.return_value = (
        "name: place_v1\nfeature_names: [speed, course]\ncat_features: [course]\n"
    )

    result = run_export_feature_contract_usecase(
        ExportFeatureContractRequest(
            registry_path="registry.yml",
            feature_set_name="place_v1",
            target_path="contracts/place_v1.yml",
            contract_name="place_v1",
            dry_run=False,
            emit_stdout=False,
            allow_create=True,
            check_only=False,
            validate_name_match=True,
            quiet=True,
        ),
        ExportFeatureContractDeps(file_gateway=files, feature_definition_port=definitions),
    )

    assert result.created is True
    assert result.changed is True
    assert result.feature_names == ["speed", "course"]
    assert result.cat_features == ["course"]
    files.write_text.assert_called_once_with("contracts/place_v1.yml", result.yaml_text)


def test_table_export_flow_returns_the_created_artifact_summary() -> None:
    files = create_autospec(FileGatewayPort, instance=True, spec_set=True)
    files.exists.return_value = False
    exporter = create_autospec(TableParquetExportPort, instance=True, spec_set=True)
    exporter.export_table.return_value = TableParquetExportArtifact(
        output_path="outputs/train.parquet",
        row_count=120,
        file_size_bytes=4096,
        compression="zstd",
    )

    result = run_export_table_to_parquet_usecase(
        ExportTableToParquetRequest(
            source_table="mart.train_features",
            output_path="outputs/train.parquet",
            where={"held_year": 2025},
            compression="zstd",
            overwrite=False,
            quiet=True,
        ),
        ExportTableToParquetDeps(file_gateway=files, parquet_exporter=exporter),
    )

    assert result.source_table == "mart.train_features"
    assert result.output_path == "outputs/train.parquet"
    assert result.row_count == 120
    assert result.file_size_bytes == 4096
    assert result.compression == "zstd"


def test_mlflow_migration_flow_copies_and_rewrites_the_store(tmp_path: Path) -> None:
    source_dir = str((tmp_path / "legacy").resolve())
    target_dir = str((tmp_path / "target").resolve())
    source_meta = str(Path(source_dir) / "1" / "meta.yaml")
    source_artifact = str(Path(source_dir) / "1" / "run-1" / "artifacts" / "summary.json")

    files = create_autospec(FileGatewayPort, instance=True, spec_set=True)
    files.exists.side_effect = lambda path: path == source_dir
    files.list_files.return_value = [source_meta, source_artifact]
    files.list_dirs.return_value = [str(Path(source_dir) / "1")]
    files.read_text.return_value = f"artifact_location: {source_dir}/1\n"

    store = create_autospec(MlflowStorePort, instance=True, spec_set=True)
    store.resolve_local_store_dir.return_value = target_dir
    store.rewrite_meta_for_target.return_value = f"artifact_location: {target_dir}/1\n"
    store.verify_store_readable.return_value = MlflowStoreVerification(
        experiment_names=("feature_validation",),
    )

    result = run_migrate_mlflow_store_usecase(
        MlflowStoreMigrationRequest(
            source_store_dir=source_dir,
            target_tracking_uri=Path(target_dir).as_uri(),
            check_only=False,
        ),
        MlflowStoreMigrationDeps(file_gateway=files, mlflow_store_port=store),
    )

    assert result.target_store_dir == target_dir
    assert result.rewritten_meta_files == ("1/meta.yaml",)
    assert result.copied_files == ("1/run-1/artifacts/summary.json",)
    assert result.verified_experiment_names == ("feature_validation",)
    files.write_text.assert_called_once_with(
        str(Path(target_dir) / "1" / "meta.yaml"),
        f"artifact_location: {target_dir}/1\n",
    )
    files.copy.assert_called_once_with(
        source_artifact,
        str(Path(target_dir) / "1" / "run-1" / "artifacts" / "summary.json"),
    )


def test_condition_tracking_flow_publishes_the_report_as_domain_output() -> None:
    reader = create_autospec(ConditionSplitReportReaderPort, instance=True, spec_set=True)
    reader.read_report.return_value = ConditionSplitReport(
        summary_row={
            "condition_column": "distance_bucket",
            "split_mode": "manual_bins",
            "primary_metric": "auc",
            "auc": "0.72",
            "logloss": "0.41",
        },
        slice_rows=(
            {"condition": "short", "auc": "0.70"},
            {"condition": "long", "auc": "0.74"},
        ),
    )
    publisher = create_autospec(ConditionTrackingPublisherPort, instance=True, spec_set=True)
    publisher.publish.return_value = "run-42"

    result = run_log_condition_split_compare_usecase(
        ConditionSplitCompareTrackingRequest(
            experiment_name="condition-split",
            run_name="distance",
            summary_csv_path="summary.csv",
            slices_csv_path="slices.csv",
            parent_run_id="parent-1",
            tags={"git_commit": "abc123"},
        ),
        ConditionSplitCompareTrackingDeps(report_reader=reader, publisher=publisher),
    )

    assert result.run_id == "run-42"
    assert result.slice_count == 2
    assert result.metric_keys == ("auc", "logloss")
    assert result.param_keys == (
        "condition_column",
        "parent_run_id",
        "primary_metric",
        "slice_count",
        "slices_csv_path",
        "split_mode",
        "summary_csv_path",
    )
    published_payload = publisher.publish.call_args.kwargs["payload"]
    assert published_payload.metrics == {"auc": 0.72, "logloss": 0.41}
    assert published_payload.tags["git_commit"] == "abc123"
