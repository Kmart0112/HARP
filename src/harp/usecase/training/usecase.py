from __future__ import annotations

from harp.core.training import (
    CalibrationMethod,
    TrainingTaskSpec,
    build_training_artifact_payload,
    build_training_recipe,
    fit_platt_logodds_oof,
    train_binary_lgbm,
)

from .common import TrainFlowResult, materialize_dataset, persist_training_outputs
from .dto import TrainDeps, TrainRequest


def _skip_calibration(
    *,
    req: TrainRequest,
    df_train,
    ds,
    model,
) -> dict | None:
    return None


def _fit_platt_calibration(
    *,
    req: TrainRequest,
    df_train,
    ds,
    model,
) -> dict | None:
    return fit_platt_logodds_oof(
        model=model,
        ds=ds,
        df_meta=df_train,
        odds_col=str(req.calibration_odds_col).strip(),
        train_year_start=req.train_year_start,
        train_year_end=req.train_year_end,
    )


CALIBRATION_FITTERS = {
    CalibrationMethod.NONE: _skip_calibration,
    CalibrationMethod.PLATT_LOGODDS: _fit_platt_calibration,
}


def _start_tracking_run(
    *,
    req: TrainRequest,
    deps: TrainDeps,
    task_spec: TrainingTaskSpec,
) -> str | None:
    if deps.tracking_port is None or req.tracking_experiment_name is None:
        return None

    run_name = req.tracking_run_name or f"train_{task_spec.model_type.value}"
    run_id = deps.tracking_port.start_run(
        experiment_name=req.tracking_experiment_name,
        run_name=run_name,
        tags={
            "source": "train_pipeline",
            "pipeline_kind": req.pipeline_kind.value,
            "model_type": task_spec.model_type.value,
            "calibration_method": req.calibration_method.value,
        },
    )
    deps.tracking_port.log_params(
        run_id,
        {
            "pipeline_kind": req.pipeline_kind.value,
            "feature_set_name": req.feature_set_name,
            "train_year_start": req.train_year_start,
            "train_year_end": req.train_year_end,
            "test_year": req.test_year,
            "artifact_out": req.artifact_out,
            "manifest_out": req.manifest_out,
            "legacy_copy": req.legacy_copy,
            "legacy_artifact_out": req.legacy_artifact_out,
            "calibration_method": req.calibration_method.value,
            "calibration_odds_col": req.calibration_odds_col,
            "mart_table": deps.mart_table,
            "source_table": deps.source_table,
        },
    )
    return run_id


def _finish_tracking_run(
    *,
    req: TrainRequest,
    deps: TrainDeps,
    tracking_run_id: str | None,
    result: TrainFlowResult,
) -> None:
    if deps.tracking_port is None or tracking_run_id is None:
        return

    metrics = {key: float(value) for key, value in result.metrics.items() if value is not None}
    if metrics:
        deps.tracking_port.log_metrics(tracking_run_id, metrics)
    deps.tracking_port.log_params(
        tracking_run_id,
        {
            "train_rows": result.train_rows,
            "val_rows": result.val_rows,
            "test_rows": result.test_rows,
        },
    )
    deps.tracking_port.log_artifact(tracking_run_id, req.artifact_out, artifact_path="model")
    deps.tracking_port.log_artifact(tracking_run_id, req.manifest_out, artifact_path="metadata")
    deps.tracking_port.log_dict(
        tracking_run_id,
        {
            "artifact_out": result.artifact_out,
            "manifest_out": result.manifest_out,
            "legacy_artifact_out": result.legacy_artifact_out,
            "metrics": result.metrics,
            "calibration_info": result.calibration_info,
        },
        artifact_file="training_summary.json",
    )
    deps.tracking_port.set_terminated(tracking_run_id, status="FINISHED")


def run_train_pipeline_usecase(req: TrainRequest, deps: TrainDeps) -> TrainFlowResult:
    task_spec = req.task_spec
    tracking_run_id = _start_tracking_run(req=req, deps=deps, task_spec=task_spec)
    try:
        df_train, ds = materialize_dataset(
            training_repository=deps.training_repository,
            feature_definition_port=deps.feature_definition_port,
            mart_table=deps.mart_table,
            contract_path=deps.contract_path,
            feature_set_name=req.feature_set_name,
            target_col=task_spec.target_col,
            train_year_start=req.train_year_start,
            train_year_end=req.train_year_end,
            test_year=req.test_year,
            limit=req.limit,
            where=req.where,
        )
        training_recipe = build_training_recipe(task_kind=task_spec.task_kind, ds=ds)

        result = train_binary_lgbm(
            ds,
            model_params=training_recipe.model_params,
            fit_kwargs=training_recipe.fit_kwargs,
        )

        calibration_fitter = CALIBRATION_FITTERS[req.calibration_method]
        calibration_info = calibration_fitter(
            req=req,
            df_train=df_train,
            ds=ds,
            model=result.model,
        )

        payload = build_training_artifact_payload(
            model=result.model,
            model_type=task_spec.model_type.value,
            feature_names=ds.feature_names,
            cat_features=ds.cat_features,
            split_info=ds.split_info,
            metrics=result.metrics,
            note=task_spec.note,
            calibration_method=req.calibration_method.value,
            calibration_info=calibration_info,
        )
        legacy_path = persist_training_outputs(
            artifact_store_port=deps.artifact_store_port,
            manifest_store_port=deps.manifest_store_port,
            payload=payload,
            model_type=task_spec.model_type.value,
            artifact_out=req.artifact_out,
            manifest_out=req.manifest_out,
            legacy_copy=req.legacy_copy,
            legacy_artifact_out=req.legacy_artifact_out,
            feature_names=ds.feature_names,
            cat_features=ds.cat_features,
            train_year_start=req.train_year_start,
            train_year_end=req.train_year_end,
            test_year=req.test_year,
            metrics=result.metrics,
            source_table=deps.source_table,
            note=task_spec.note,
            calibration_method=req.calibration_method.value,
        )

        flow_result = TrainFlowResult(
            train_rows=len(ds.X_tr),
            val_rows=len(ds.X_val),
            test_rows=len(ds.X_test),
            artifact_out=req.artifact_out,
            manifest_out=req.manifest_out,
            legacy_artifact_out=legacy_path,
            metrics=result.metrics,
            calibration_info=calibration_info,
            tracking_run_id=tracking_run_id,
        )
        _finish_tracking_run(req=req, deps=deps, tracking_run_id=tracking_run_id, result=flow_result)
        return flow_result
    except Exception:
        if deps.tracking_port is not None and tracking_run_id is not None:
            deps.tracking_port.set_terminated(tracking_run_id, status="FAILED")
        raise
