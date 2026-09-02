import marimo

__generated_with = "0.20.4"
app = marimo.App(width="medium")


@app.cell
def _():
    # セル概要: notebookで利用する依存を読み込む。
    from datetime import datetime
    import json
    import os
    import shutil
    import sys
    from pathlib import Path
    from zoneinfo import ZoneInfo

    import marimo as mo
    import matplotlib.pyplot as plt
    import pandas as pd
    import shap
    from pydantic import BaseModel, Field

    return (
        BaseModel,
        Field,
        Path,
        ZoneInfo,
        datetime,
        json,
        mo,
        os,
        pd,
        plt,
        shap,
        shutil,
        sys,
    )


@app.cell
def _(Path, sys):
    # セル概要: プロジェクトルートと共通 helper を解決する。
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    SRC_ROOT = PROJECT_ROOT / "src"
    NOTEBOOK_ROOT = PROJECT_ROOT / "notebook" / "lab"

    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    from harp.adapters.driven.db import PostgresTrainingRepositoryAdapter
    from harp.controllers import build_notebook_config, infer_predict_manifest_path
    from harp.adapters.driven.storage import (
        LocalFileGatewayAdapter,
        PickleModelLoaderAdapter,
        dataframe_cache_exists,
        load_dataframe_cache,
        resolve_dataframe_cache_path,
        save_dataframe_cache,
    )
    from harp.core.explainability import (
        ShapMetricsContext,
        build_candidate_shap_artifact_summary,
        build_shap_review_figure_filename,
        build_shap_review_report_stem,
        build_shap_review_run_id,
        render_candidate_shap_full_report_markdown,
    )
    from harp.shared.paths import notebook_analysis_cache_dir
    from harp.usecase import (
        CandidateFeatureShapReviewDeps,
        CandidateFeatureShapReviewRequest,
        run_candidate_feature_shap_review_usecase,
    )
    from pipeline.runtime_settings import load_pipeline_runtime_config

    CACHE_DIR = notebook_analysis_cache_dir()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    runtime_config = load_pipeline_runtime_config()
    return (
        CACHE_DIR,
        CandidateFeatureShapReviewDeps,
        CandidateFeatureShapReviewRequest,
        LocalFileGatewayAdapter,
        PROJECT_ROOT,
        PickleModelLoaderAdapter,
        PostgresTrainingRepositoryAdapter,
        ShapMetricsContext,
        build_candidate_shap_artifact_summary,
        build_notebook_config,
        build_shap_review_figure_filename,
        build_shap_review_report_stem,
        build_shap_review_run_id,
        dataframe_cache_exists,
        infer_predict_manifest_path,
        load_dataframe_cache,
        render_candidate_shap_full_report_markdown,
        resolve_dataframe_cache_path,
        run_candidate_feature_shap_review_usecase,
        runtime_config,
        save_dataframe_cache,
    )


@app.cell
def _(mo):
    # セル概要: notebook のタイトルと説明を表示する。
    mo.md(
        "\n".join(
            [
                "# LightGBM Place SHAP Feature Review",
                "",
                "- 候補特徴 1 本の採用可否レビューに特化する",
                "- metrics が未改善でも SHAP は必ず実施する",
                "- 説明対象は base LightGBM only",
                "- 保存済み artifact と再構築 dataset を利用する",
            ]
        )
    )
    return


@app.cell
def _(mo):
    # セル概要: script 実行か interactive 実行かを判定する。
    is_script_mode = mo.app_meta().mode == "script"
    return (is_script_mode,)


@app.cell
def _(BaseModel, Field, runtime_config):
    # セル概要: notebook 全体の既定設定を定義する。
    class AppConfig(BaseModel):
        db_url: str = Field(default="")
        read_from_db_default: bool = Field(default=False)
        artifact_path: str = Field(
            default="notebook/prd/outputs/artifacts/is_place_notebook_v1.pkl"
        )
        sample_split: str = Field(default="val")
        sample_size: int = Field(default=3000)
        validation_mode: str = Field(default="single_add")
        metrics_run_label: str = Field(default="candidate_review")
        delta_auc: float = Field(default=0.0)
        delta_logloss: float = Field(default=0.0)
        delta_brier: float = Field(default=0.0)
        candidate_feature: str = Field(default="")
        comparison_feature_1: str = Field(default="")
        comparison_feature_2: str = Field(default="")
        comparison_feature_3: str = Field(default="")
        held_year_min: int | None = Field(default=None)
        held_year_max: int | None = Field(default=None)
        artifact_root_dir: str = Field(default="notebook/lab/tmp/shap_reviews")
        report_run_label: str = Field(default="")
        write_artifact_bundle_default: bool = Field(default=True)
        write_official_report_default: bool = Field(default=True)

    cfg = AppConfig(db_url=runtime_config.database.db_url)
    return AppConfig, cfg


@app.cell
def _(cfg, mo):
    # セル概要: artifact 読込とデータ読込の UI を表示する。
    artifact_root_dir_widget = mo.ui.text(
        label="Artifact bundle root",
        value=cfg.artifact_root_dir,
        full_width=True,
    )
    db_url_widget = mo.ui.text(
        label="HARP_DB_URL",
        value=cfg.db_url,
        placeholder="Set HARP_DB_URL in your local .env",
        full_width=True,
    )
    read_from_db_switch = mo.ui.switch(value=cfg.read_from_db_default, label="Read from DB")
    artifact_path_widget = mo.ui.text(
        label="Artifact path",
        value=cfg.artifact_path,
        full_width=True,
    )
    split_widget = mo.ui.dropdown(
        options=["val", "train", "test"],
        value=cfg.sample_split,
        label="Sample split",
    )
    sample_size_widget = mo.ui.number(
        start=100,
        step=100,
        value=cfg.sample_size,
        label="Sample size cap",
    )

    mo.vstack(
        [
            mo.md("## 1. Artifact / Data Source"),
            db_url_widget,
            mo.hstack([read_from_db_switch, split_widget, sample_size_widget]),
            artifact_path_widget,
            artifact_root_dir_widget,
            mo.md("`Read from DB` OFF の場合は cache を優先し、無ければ DB にフォールバックする。"),
        ]
    )
    return (
        artifact_path_widget,
        artifact_root_dir_widget,
        db_url_widget,
        read_from_db_switch,
        sample_size_widget,
        split_widget,
    )


@app.cell
def _(
    AppConfig,
    artifact_path_widget,
    artifact_root_dir_widget,
    build_notebook_config,
    cfg,
    db_url_widget,
    is_script_mode,
    mo,
    read_from_db_switch,
    sample_size_widget,
    split_widget,
):
    # セル概要: 実行モードごとの入力値を解決する。
    if is_script_mode:
        app_cfg = build_notebook_config(AppConfig, defaults=cfg, cli_args=mo.cli_args())
    else:
        app_cfg = build_notebook_config(
            AppConfig,
            defaults=cfg,
            overrides={
                "artifact_path": str(artifact_path_widget.value).strip(),
                "artifact_root_dir": str(artifact_root_dir_widget.value).strip(),
                "db_url": str(db_url_widget.value).strip(),
                "read_from_db_default": bool(read_from_db_switch.value),
                "sample_size": int(sample_size_widget.value),
                "sample_split": str(split_widget.value),
            },
        )

    app_cfg = app_cfg.model_copy(
        update={
            "artifact_path": str(app_cfg.artifact_path).strip(),
            "artifact_root_dir": str(app_cfg.artifact_root_dir).strip(),
            "candidate_feature": str(app_cfg.candidate_feature).strip(),
            "comparison_feature_1": str(app_cfg.comparison_feature_1).strip(),
            "comparison_feature_2": str(app_cfg.comparison_feature_2).strip(),
            "comparison_feature_3": str(app_cfg.comparison_feature_3).strip(),
            "db_url": str(app_cfg.db_url).strip(),
            "metrics_run_label": str(app_cfg.metrics_run_label).strip(),
            "report_run_label": str(app_cfg.report_run_label).strip(),
            "sample_split": str(app_cfg.sample_split).strip(),
            "validation_mode": str(app_cfg.validation_mode).strip(),
            "write_artifact_bundle_default": bool(app_cfg.write_artifact_bundle_default),
            "write_official_report_default": bool(app_cfg.write_official_report_default),
        }
    )

    app_cfg = app_cfg.model_copy(
        update={
            "report_run_label": app_cfg.report_run_label or app_cfg.metrics_run_label,
        }
    )

    if not app_cfg.artifact_path:
        raise ValueError("Artifact path is required.")
    if not app_cfg.artifact_root_dir:
        raise ValueError("artifact_root_dir is required.")
    return (app_cfg,)


@app.cell
def _(
    LocalFileGatewayAdapter,
    PickleModelLoaderAdapter,
    app_cfg,
    infer_predict_manifest_path,
    json,
):
    # セル概要: artifact payload と対応 manifest を読み込む。
    file_gateway = LocalFileGatewayAdapter()
    loader = PickleModelLoaderAdapter(file_gateway=file_gateway)
    payload = loader.load_model_payload(app_cfg.artifact_path)

    resolved_manifest_path = infer_predict_manifest_path(app_cfg.artifact_path)
    if resolved_manifest_path and file_gateway.exists(resolved_manifest_path):
        manifest = json.loads(file_gateway.read_text(resolved_manifest_path))
    else:
        manifest = None
    return manifest, payload, resolved_manifest_path


@app.cell
def _(app_cfg, manifest, mo, payload, resolved_manifest_path):
    # セル概要: artifact / manifest の読込結果を表示する。
    model_type = str(payload.get("model_type", "unknown"))
    note = str(payload.get("note", ""))
    calibration = payload.get("calibration")
    has_platt = (
        isinstance(calibration, dict)
        and str(calibration.get("method") or "").strip().lower() == "platt_logodds"
        and isinstance(calibration.get("params"), dict)
    )
    manifest_text = resolved_manifest_path if manifest is not None else "not found"

    mo.vstack(
        [
            mo.md("## 2. Artifact Summary"),
            mo.md(f"- artifact: `{app_cfg.artifact_path}`"),
            mo.md(f"- manifest: `{manifest_text}`"),
            mo.md(f"- model_type: `{model_type}`"),
            mo.md(f"- note: `{note}`"),
            mo.md(f"- calibration payload: `{'calibration.params' if has_platt else 'none'}`"),
            mo.md("SHAP explanation target: `base LightGBM only`"),
        ]
    )
    return


@app.cell
def _(payload):
    # セル概要: split 情報から cache path を決める。
    _split_info = payload.get("split_info")
    if not isinstance(_split_info, dict):
        raise KeyError("Artifact payload does not include valid 'split_info'.")

    train_year_start = int(_split_info["train_year_start"])
    train_year_end = int(_split_info["train_year_end"])
    test_year = int(_split_info["test_year"])
    return test_year, train_year_end, train_year_start


@app.cell
def _(CACHE_DIR, test_year, train_year_start):
    # セル概要: 学習フレーム cache の保存先を解決する。
    cache_path = CACHE_DIR / f"m_train_race_horse_past5_{train_year_start}_{test_year}.parquet"
    return (cache_path,)


@app.cell
def _(
    PostgresTrainingRepositoryAdapter,
    app_cfg,
    cache_path,
    dataframe_cache_exists,
    load_dataframe_cache,
    resolve_dataframe_cache_path,
    save_dataframe_cache,
    test_year,
    train_year_end,
):
    # セル概要: 学習フレームを cache 優先で取得する。
    has_cache = dataframe_cache_exists(cache_path)
    if not app_cfg.read_from_db_default and has_cache:
        cache_source_path = resolve_dataframe_cache_path(cache_path)
        print(f"[cache] loading from {cache_source_path}")
        df_train = load_dataframe_cache(cache_path)
    else:
        if not app_cfg.db_url:
            raise ValueError("HARP_DB_URL is required when cache is missing or DB refresh is enabled.")
        print("[db] querying mart.m_train_race_horse_past5 for SHAP review ...")
        repo = PostgresTrainingRepositoryAdapter(db_url=app_cfg.db_url)
        df_train = repo.load_training_frame(
            max_year=max(int(train_year_end), int(test_year)),
            limit=None,
            mart_table="mart.m_train_race_horse_past5",
            where={"race_level__gte": 1, "race_level__lte": 3},
        )
        save_dataframe_cache(df_train, cache_path)
        print(f"[cache] saved to {cache_path}")
    return (df_train,)


@app.cell
def _(app_cfg, df_train, mo, payload, pd, split_widget):
    # セル概要: 候補特徴レビューの UI を構築する。
    _years = pd.to_numeric(df_train["held_year"], errors="coerce") if "held_year" in df_train.columns else pd.to_datetime(df_train["held_date"], errors="coerce").dt.year
    _years = pd.Series(_years).dropna().astype(int)
    if _years.empty:
        raise ValueError("held_year/held_date is required for SHAP review.")

    _feature_names = list(payload["feature_names"])
    candidate_default = (
        app_cfg.candidate_feature
        if app_cfg.candidate_feature in _feature_names
        else _feature_names[0]
    )
    candidate_feature_widget = mo.ui.dropdown(
        options=_feature_names,
        value=candidate_default,
        searchable=True,
        label="Candidate feature",
        full_width=True,
    )
    comparison_options = {"None": "", **{name: name for name in _feature_names}}
    comparison_default_1 = (
        app_cfg.comparison_feature_1 if app_cfg.comparison_feature_1 in _feature_names else "None"
    )
    comparison_default_2 = (
        app_cfg.comparison_feature_2 if app_cfg.comparison_feature_2 in _feature_names else "None"
    )
    comparison_default_3 = (
        app_cfg.comparison_feature_3 if app_cfg.comparison_feature_3 in _feature_names else "None"
    )
    comparison_feature_widget_1 = mo.ui.dropdown(
        options=comparison_options,
        value=comparison_default_1,
        searchable=True,
        label="Comparison feature 1",
        full_width=True,
    )
    comparison_feature_widget_2 = mo.ui.dropdown(
        options=comparison_options,
        value=comparison_default_2,
        searchable=True,
        label="Comparison feature 2",
        full_width=True,
    )
    comparison_feature_widget_3 = mo.ui.dropdown(
        options=comparison_options,
        value=comparison_default_3,
        searchable=True,
        label="Comparison feature 3",
        full_width=True,
    )
    held_year_start = (
        int(_years.min())
        if app_cfg.held_year_min is None
        else max(int(app_cfg.held_year_min), int(_years.min()))
    )
    held_year_end = (
        int(_years.max())
        if app_cfg.held_year_max is None
        else min(int(app_cfg.held_year_max), int(_years.max()))
    )
    held_year_range_widget = mo.ui.range_slider(
        start=int(_years.min()),
        stop=int(_years.max()),
        step=1,
        value=[held_year_start, max(held_year_start, held_year_end)],
        show_value=True,
        label="held_year range",
        full_width=True,
    )
    validation_mode_widget = mo.ui.dropdown(
        options=["single_add", "overlap", "keep_drop"],
        value=app_cfg.validation_mode,
        label="Validation mode",
    )
    metrics_run_label_widget = mo.ui.text(
        label="Metrics run label",
        value=app_cfg.metrics_run_label,
        full_width=True,
    )
    delta_auc_widget = mo.ui.number(
        value=app_cfg.delta_auc,
        step=0.0001,
        start=-1.0,
        stop=1.0,
        label="DeltaAUC",
    )
    delta_logloss_widget = mo.ui.number(
        value=app_cfg.delta_logloss,
        step=0.0001,
        start=-1.0,
        stop=1.0,
        label="DeltaLogLoss",
    )
    delta_brier_widget = mo.ui.number(
        value=app_cfg.delta_brier,
        step=0.0001,
        start=-1.0,
        stop=1.0,
        label="DeltaBrier",
    )
    report_run_label_widget = mo.ui.text(
        label="Report run label",
        value=app_cfg.report_run_label or app_cfg.metrics_run_label,
        full_width=True,
    )
    write_artifact_bundle_switch = mo.ui.switch(
        value=app_cfg.write_artifact_bundle_default,
        label="Write artifact bundle",
    )
    write_official_report_switch = mo.ui.switch(
        value=app_cfg.write_official_report_default,
        label="Write official SHAP report",
    )
    run_review_button = mo.ui.run_button(label="Run Candidate Review")

    mo.vstack(
        [
            mo.md("## 3. Review Context"),
            mo.hstack([split_widget, held_year_range_widget]),
            candidate_feature_widget,
            mo.hstack(
                [
                    comparison_feature_widget_1,
                    comparison_feature_widget_2,
                    comparison_feature_widget_3,
                ]
            ),
            mo.hstack([validation_mode_widget, metrics_run_label_widget]),
            mo.hstack([delta_auc_widget, delta_logloss_widget, delta_brier_widget]),
            report_run_label_widget,
            mo.hstack([write_artifact_bundle_switch, write_official_report_switch]),
            run_review_button,
        ]
    )
    return (
        candidate_feature_widget,
        comparison_feature_widget_1,
        comparison_feature_widget_2,
        comparison_feature_widget_3,
        delta_auc_widget,
        delta_brier_widget,
        delta_logloss_widget,
        held_year_range_widget,
        metrics_run_label_widget,
        report_run_label_widget,
        run_review_button,
        validation_mode_widget,
        write_artifact_bundle_switch,
        write_official_report_switch,
    )


@app.cell
def _(is_script_mode, run_review_button):
    # セル概要: script では自動実行、interactive では明示実行にする。
    should_run_review = is_script_mode or bool(run_review_button.value)
    return (should_run_review,)


@app.cell
def _(
    AppConfig,
    app_cfg,
    build_notebook_config,
    candidate_feature_widget,
    comparison_feature_widget_1,
    comparison_feature_widget_2,
    comparison_feature_widget_3,
    delta_auc_widget,
    delta_brier_widget,
    delta_logloss_widget,
    df_train,
    held_year_range_widget,
    is_script_mode,
    metrics_run_label_widget,
    pd,
    payload,
    report_run_label_widget,
    sample_size_widget,
    split_widget,
    validation_mode_widget,
    write_artifact_bundle_switch,
    write_official_report_switch,
):
    # セル概要: review 実行に使う設定値を最終正規化する。
    _feature_names = list(payload["feature_names"])
    _years = pd.to_numeric(df_train["held_year"], errors="coerce") if "held_year" in df_train.columns else pd.to_datetime(df_train["held_date"], errors="coerce").dt.year
    _years = pd.Series(_years).dropna().astype(int)
    if _years.empty:
        raise ValueError("held_year/held_date is required for SHAP review.")

    year_min = int(_years.min())
    year_max = int(_years.max())
    if is_script_mode:
        candidate_feature = str(app_cfg.candidate_feature).strip()
        if not candidate_feature:
            raise ValueError("candidate_feature is required in script mode.")
        review_cfg = build_notebook_config(
            AppConfig,
            defaults=app_cfg,
            overrides={
                "candidate_feature": candidate_feature,
                "held_year_max": year_max if app_cfg.held_year_max is None else int(app_cfg.held_year_max),
                "held_year_min": year_min if app_cfg.held_year_min is None else int(app_cfg.held_year_min),
            },
        )
    else:
        review_cfg = build_notebook_config(
            AppConfig,
            defaults=app_cfg,
            overrides={
                "candidate_feature": str(candidate_feature_widget.value).strip(),
                "comparison_feature_1": str(comparison_feature_widget_1.value).strip(),
                "comparison_feature_2": str(comparison_feature_widget_2.value).strip(),
                "comparison_feature_3": str(comparison_feature_widget_3.value).strip(),
                "delta_auc": float(delta_auc_widget.value),
                "delta_brier": float(delta_brier_widget.value),
                "delta_logloss": float(delta_logloss_widget.value),
                "held_year_max": int(held_year_range_widget.value[1]),
                "held_year_min": int(held_year_range_widget.value[0]),
                "metrics_run_label": str(metrics_run_label_widget.value).strip(),
                "report_run_label": str(report_run_label_widget.value).strip(),
                "sample_size": max(int(sample_size_widget.value), 1),
                "sample_split": str(split_widget.value),
                "validation_mode": str(validation_mode_widget.value).strip(),
                "write_artifact_bundle_default": bool(write_artifact_bundle_switch.value),
                "write_official_report_default": bool(write_official_report_switch.value),
            },
        )

    review_cfg = review_cfg.model_copy(
        update={
            "candidate_feature": str(review_cfg.candidate_feature).strip(),
            "comparison_feature_1": str(review_cfg.comparison_feature_1).strip(),
            "comparison_feature_2": str(review_cfg.comparison_feature_2).strip(),
            "comparison_feature_3": str(review_cfg.comparison_feature_3).strip(),
            "held_year_max": min(int(review_cfg.held_year_max), year_max),
            "held_year_min": max(int(review_cfg.held_year_min), year_min),
            "metrics_run_label": str(review_cfg.metrics_run_label).strip(),
            "report_run_label": str(review_cfg.report_run_label).strip(),
            "sample_size": max(int(review_cfg.sample_size), 1),
            "sample_split": str(review_cfg.sample_split).strip(),
            "validation_mode": str(review_cfg.validation_mode).strip(),
            "write_artifact_bundle_default": bool(review_cfg.write_artifact_bundle_default),
            "write_official_report_default": bool(review_cfg.write_official_report_default),
        }
    )

    review_cfg = review_cfg.model_copy(
        update={
            "report_run_label": review_cfg.report_run_label or review_cfg.metrics_run_label,
            "write_artifact_bundle_default": bool(
                review_cfg.write_artifact_bundle_default or review_cfg.write_official_report_default
            ),
        }
    )

    if review_cfg.candidate_feature not in _feature_names:
        raise ValueError(f"Unknown candidate_feature: {review_cfg.candidate_feature}")
    comparison_feature_updates = {}
    for field_name in ("comparison_feature_1", "comparison_feature_2", "comparison_feature_3"):
        comparison_feature = str(getattr(review_cfg, field_name)).strip()
        if comparison_feature and comparison_feature not in _feature_names:
            comparison_feature_updates[field_name] = ""
    if comparison_feature_updates:
        review_cfg = review_cfg.model_copy(update=comparison_feature_updates)
    if review_cfg.sample_split not in {"val", "train", "test"}:
        raise ValueError(f"Unsupported sample_split: {review_cfg.sample_split}")
    if review_cfg.validation_mode not in {"single_add", "overlap", "keep_drop"}:
        raise ValueError(f"Unsupported validation_mode: {review_cfg.validation_mode}")
    if int(review_cfg.held_year_min) > int(review_cfg.held_year_max):
        raise ValueError("held_year_min must be <= held_year_max.")
    return (review_cfg,)


@app.cell
def _(
    CandidateFeatureShapReviewDeps,
    CandidateFeatureShapReviewRequest,
    ShapMetricsContext,
    df_train,
    payload,
    review_cfg,
    run_candidate_feature_shap_review_usecase,
    should_run_review,
):
    # セル概要: 候補特徴レビューの集計を実行する。
    if not should_run_review:
        review_result = None
    else:
        class _UnusedTrainingRepository:
            def load_training_frame(self, max_year, limit, mart_table, where=None):  # noqa: ANN001, D401
                raise RuntimeError("training_repository should not be called when df_train is provided.")

        comparison_features = [
            review_cfg.comparison_feature_1,
            review_cfg.comparison_feature_2,
            review_cfg.comparison_feature_3,
        ]
        review_result = run_candidate_feature_shap_review_usecase(
            req=CandidateFeatureShapReviewRequest(
                payload=payload,
                target_col="is_place",
                candidate_feature=review_cfg.candidate_feature,
                comparison_features=comparison_features,
                split=review_cfg.sample_split,
                held_year_range=(int(review_cfg.held_year_min), int(review_cfg.held_year_max)),
                sample_size_cap=max(int(review_cfg.sample_size), 1),
                metrics_context=ShapMetricsContext(
                    delta_auc=float(review_cfg.delta_auc),
                    delta_logloss=float(review_cfg.delta_logloss),
                    delta_brier=float(review_cfg.delta_brier),
                    metrics_run_label=review_cfg.metrics_run_label,
                    validation_mode=review_cfg.validation_mode,
                ),
                df_train=df_train,
            ),
            deps=CandidateFeatureShapReviewDeps(
                training_repository=_UnusedTrainingRepository(),
                mart_table="mart.m_train_race_horse_past5",
            ),
        )
    return (review_result,)


@app.cell
def _(mo, payload, review_result):
    # セル概要: 再構築した dataset の要約を表示する。
    if review_result is None:
        dataset_summary_view = mo.md("## 4. Rebuilt Dataset\n\nRun review to rebuild dataset.")
    else:
        _split_info = review_result.ds.split_info
        dataset_summary_view = mo.vstack(
            [
                mo.md("## 4. Rebuilt Dataset"),
                mo.md(f"- features: `{len(payload['feature_names']):,}`"),
                mo.md(f"- train rows: `{_split_info['n_train_rows']:,}`"),
                mo.md(f"- val rows: `{_split_info['n_val_rows']:,}`"),
                mo.md(f"- test rows: `{_split_info['n_test_rows']:,}`"),
            ]
        )
    dataset_summary_view
    return


@app.cell
def _(mo, pd, review_result):
    # セル概要: metrics gate を表示する。
    if review_result is None:
        metrics_gate_view = mo.md("## 5. Metrics Gate\n\nRun review to evaluate metrics context.")
    else:
        _verdict = review_result.review.verdict
        _metrics_context = review_result.review.metrics_context
        gate_table = pd.DataFrame(
            [
                {
                    "metrics_run_label": _metrics_context.metrics_run_label,
                    "validation_mode": _metrics_context.validation_mode,
                    "delta_auc": _metrics_context.delta_auc,
                    "delta_logloss": _metrics_context.delta_logloss,
                    "delta_brier": _metrics_context.delta_brier,
                    "metrics_judgement": _verdict.metrics_judgement,
                }
            ]
        )
        metrics_gate_view = mo.vstack(
            [
                mo.md("## 5. Metrics Gate"),
                mo.md("metrics が未改善でも SHAP review は継続する。"),
                mo.ui.table(gate_table),
            ]
        )
    return (metrics_gate_view,)


@app.cell
def _(mo, pd, review_result):
    # セル概要: candidate summary を表示する。
    if review_result is None:
        candidate_summary_view = mo.md("## 6. Candidate Summary\n\nRun review to see candidate summary.")
    else:
        _summary = review_result.review.candidate_summary
        candidate_table = pd.DataFrame(
            [
                {
                    "feature": _summary.feature,
                    "global_rank": _summary.global_rank,
                    "mean_abs_shap": _summary.mean_abs_shap,
                    "importance_share": _summary.importance_share,
                    "top_n_hit": _summary.top_n_hit,
                    "sample_rows": _summary.sample_rows,
                    "split": _summary.split,
                    "held_year_min": _summary.held_year_min,
                    "held_year_max": _summary.held_year_max,
                    "interaction_feature": _summary.interaction_feature or "",
                    "outlier_share_top1pct": _summary.outlier_share_top1pct,
                }
            ]
        )
        candidate_summary_view = mo.vstack(
            [
                mo.md("## 6. Candidate Summary"),
                mo.ui.table(candidate_table),
            ]
        )
    return (candidate_summary_view,)


@app.cell
def _(mo, plt, review_result, shap):
    # セル概要: candidate dependence を表示する。
    if review_result is None:
        dependence_view = mo.md("## 7. Candidate Dependence\n\nRun review to see dependence plot.")
        dependence_fig = None
    else:
        _package = review_result.review.shap_package
        color_explanation = (
            _package.explanation[:, _package.interaction_feature]
            if _package.interaction_feature
            else None
        )
        plt.figure(figsize=(10, 6))
        shap.plots.scatter(
            _package.explanation[:, _package.candidate_feature],
            color=color_explanation,
            show=False,
        )
        dependence_fig = plt.gcf()
        dependence_view = mo.vstack(
            [
                mo.md("## 7. Candidate Dependence"),
                mo.md(
                    f"- candidate: `{_package.candidate_feature}`\n"
                    f"- color: `{_package.interaction_feature or 'None'}`"
                ),
                dependence_fig,
            ]
        )
    return dependence_fig, dependence_view


@app.cell
def _(mo, review_result):
    # セル概要: local explanation summary を表示する。
    if review_result is None:
        local_case_view = mo.md("## 8. Local Cases\n\nRun review to see local case summary.")
    else:
        _case_summary = review_result.review.local_case_summary
        local_case_view = mo.vstack(
            [
                mo.md("## 8. Local Cases"),
                mo.ui.table(_case_summary),
            ]
        )
    return (local_case_view,)


@app.cell
def _(mo, plt, review_result, shap):
    # セル概要: comparison dependence を表示する。
    if review_result is None:
        redundancy_view = mo.md("## 9. Comparison Dependence\n\nRun review to compare candidate and overlap features.")
        comparison_figures = []
    else:
        _comparison_summary = review_result.review.comparison_summary
        _package = review_result.review.shap_package
        _figures = []
        comparison_figures = []
        for feature in _package.comparison_features:
            plt.figure(figsize=(9, 5))
            shap.plots.scatter(
                _package.explanation[:, feature],
                color=_package.explanation[:, _package.candidate_feature],
                show=False,
            )
            _fig = plt.gcf()
            _fig.suptitle(f"comparison feature: {feature}", y=1.02)
            _figures.append(_fig)
            comparison_figures.append(
                {
                    "feature": str(feature),
                    "figure": _fig,
                }
            )
        redundancy_view = mo.vstack(
            [
                mo.md("## 9. Comparison Dependence"),
                mo.ui.table(_comparison_summary),
                *_figures,
            ]
        )
    return comparison_figures, redundancy_view


@app.cell
def _(mo, pd, plt, review_result):
    # セル概要: 年・split ごとの変化を表示する。
    if review_result is None:
        stability_view = mo.md("## 10. Split / Year Change\n\nRun review to see split/year stability.")
        split_stability_fig = None
        year_stability_fig = None
    else:
        _split_summary = review_result.review.split_stability_summary
        _year_summary = review_result.review.year_stability_summary
        _figures = []
        split_stability_fig = None
        year_stability_fig = None
        if not _split_summary.empty:
            split_fig, split_ax = plt.subplots(figsize=(8, 4))
            split_ax.plot(
                _split_summary["split"].astype(str),
                pd.to_numeric(_split_summary["candidate_mean_abs_shap"], errors="coerce"),
                marker="o",
            )
            split_ax.set_title("Candidate mean_abs_shap by split")
            split_ax.set_ylabel("mean_abs_shap")
            _figures.append(split_fig)
            split_stability_fig = split_fig
        if not _year_summary.empty:
            year_fig, year_ax = plt.subplots(figsize=(8, 4))
            year_ax.plot(
                _year_summary["held_year"].astype(int),
                pd.to_numeric(_year_summary["candidate_mean_abs_shap"], errors="coerce"),
                marker="o",
            )
            year_ax.set_title("Candidate mean_abs_shap by held_year")
            year_ax.set_ylabel("mean_abs_shap")
            _figures.append(year_fig)
            year_stability_fig = year_fig
        stability_view = mo.vstack(
            [
                mo.md("## 10. Split / Year Change"),
                mo.ui.table(_split_summary),
                mo.ui.table(_year_summary),
                *_figures,
            ]
        )
    return split_stability_fig, stability_view, year_stability_fig


@app.cell
def _(mo, review_result):
    # セル概要: review verdict を表示する。
    if review_result is None:
        verdict_view = mo.md("## 11. Review Verdict\n\nRun review to generate verdict.")
    else:
        _verdict = review_result.review.verdict
        notes = "\n".join(f"- {note}" for note in _verdict.review_notes)
        verdict_view = mo.vstack(
            [
                mo.md("## 11. Review Verdict"),
                mo.md(
                    "\n".join(
                        [
                            f"- metrics_judgement: `{_verdict.metrics_judgement}`",
                            f"- shap_judgement: `{_verdict.shap_judgement}`",
                            f"- final_recommendation: `{_verdict.final_recommendation}`",
                            "",
                            "### Review Notes",
                            notes,
                        ]
                    )
                ),
            ]
        )
    return (verdict_view,)


@app.cell
def _(
    PROJECT_ROOT,
    Path,
    ZoneInfo,
    build_shap_review_report_stem,
    build_shap_review_run_id,
    datetime,
    review_cfg,
):
    # セル概要: artifact bundle と official SHAP report の出力先 path を解決する。
    def _resolve_root(raw_path: str) -> Path:
        candidate = Path(str(raw_path).strip())
        return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate

    report_executed_at = datetime.now(ZoneInfo("Asia/Tokyo"))
    report_date_token = report_executed_at.strftime("%Y%m%d")
    run_timestamp_token = report_executed_at.strftime("%Y%m%d_%H%M%S")
    shap_run_id = build_shap_review_run_id(run_timestamp_token, review_cfg.report_run_label)
    artifact_bundle_root = _resolve_root(review_cfg.artifact_root_dir)
    artifact_bundle_dir = artifact_bundle_root / shap_run_id
    artifact_bundle_figures_dir = artifact_bundle_dir / "figures"
    artifact_summary_path = artifact_bundle_dir / "summary.json"
    artifact_manifest_path = artifact_bundle_dir / "manifest.json"
    artifact_report_path = artifact_bundle_dir / "full_report.md"

    official_report_stem = build_shap_review_report_stem(
        report_date_token,
        review_cfg.report_run_label,
    )
    official_report_dir = PROJECT_ROOT / "notebook" / "report" / "shap"
    official_report_path = official_report_dir / f"{official_report_stem}.md"
    return (
        artifact_bundle_dir,
        artifact_bundle_figures_dir,
        artifact_bundle_root,
        artifact_manifest_path,
        artifact_report_path,
        artifact_summary_path,
        official_report_dir,
        official_report_path,
        report_executed_at,
        shap_run_id,
    )


@app.cell
def _(
    LocalFileGatewayAdapter,
    PROJECT_ROOT,
    Path,
    artifact_bundle_dir,
    artifact_bundle_figures_dir,
    artifact_manifest_path,
    artifact_report_path,
    artifact_summary_path,
    build_candidate_shap_artifact_summary,
    build_shap_review_figure_filename,
    comparison_figures,
    dependence_fig,
    json,
    official_report_dir,
    official_report_path,
    os,
    render_candidate_shap_full_report_markdown,
    report_executed_at,
    review_cfg,
    review_result,
    shap_run_id,
    shutil,
    split_stability_fig,
    year_stability_fig,
):
    # セル概要: artifact bundle と official SHAP report を保存する。
    saved_output_paths = None
    saved_report_summary = None
    if review_result is not None and (
        review_cfg.write_artifact_bundle_default or review_cfg.write_official_report_default
    ):
        if artifact_bundle_dir.exists():
            shutil.rmtree(artifact_bundle_dir)
        artifact_bundle_figures_dir.mkdir(parents=True, exist_ok=True)

        def _rel_from_bundle(path: Path) -> str:
            return path.relative_to(artifact_bundle_dir).as_posix()

        def _rel_from_project(path: Path) -> str:
            return path.relative_to(PROJECT_ROOT).as_posix()

        def _rel_from_official_report(path: Path) -> str:
            return os.path.relpath(path, start=official_report_path.parent)

        def _save_figure(path: Path, figure) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            figure.savefig(path, dpi=160, bbox_inches="tight")

        figure_manifest = {
            "figures_dir": _rel_from_bundle(artifact_bundle_figures_dir),
            "candidate_dependence": None,
            "comparison_dependence": [],
            "stability_split": None,
            "stability_year": None,
        }

        if dependence_fig is not None:
            dependence_bundle_path = artifact_bundle_figures_dir / build_shap_review_figure_filename(
                "dependence",
                feature_name=review_result.review.shap_package.candidate_feature,
            )
            _save_figure(dependence_bundle_path, dependence_fig)
            figure_manifest["candidate_dependence"] = _rel_from_bundle(dependence_bundle_path)

        for item in comparison_figures:
            comparison_path = artifact_bundle_figures_dir / build_shap_review_figure_filename(
                "dependence",
                feature_name=str(item["feature"]),
            )
            _save_figure(comparison_path, item["figure"])
            figure_manifest["comparison_dependence"].append(
                {
                    "feature": str(item["feature"]),
                    "path": _rel_from_bundle(comparison_path),
                }
            )

        if split_stability_fig is not None:
            split_path = artifact_bundle_figures_dir / build_shap_review_figure_filename("stability_split")
            _save_figure(split_path, split_stability_fig)
            figure_manifest["stability_split"] = _rel_from_bundle(split_path)

        if year_stability_fig is not None:
            year_path = artifact_bundle_figures_dir / build_shap_review_figure_filename("stability_year")
            _save_figure(year_path, year_stability_fig)
            figure_manifest["stability_year"] = _rel_from_bundle(year_path)

        saved_report_summary = build_candidate_shap_artifact_summary(
            review=review_result.review,
            run_id=shap_run_id,
            artifact_path=review_cfg.artifact_path,
            artifact_bundle_dir=_rel_from_project(artifact_bundle_dir),
            artifact_summary_path=_rel_from_project(artifact_summary_path),
            artifact_report_path=_rel_from_project(artifact_report_path),
            executed_at=report_executed_at.isoformat(),
            report_run_label=review_cfg.report_run_label,
            sample_split=review_cfg.sample_split,
            sample_size=int(review_cfg.sample_size),
            held_year_range=(int(review_cfg.held_year_min), int(review_cfg.held_year_max)),
            split_info=review_result.ds.split_info,
            figure_manifest=figure_manifest,
        )

        _file_gateway = LocalFileGatewayAdapter()
        artifact_markdown = render_candidate_shap_full_report_markdown(saved_report_summary)
        _file_gateway.write_text(str(artifact_report_path), artifact_markdown)
        _file_gateway.write_text(
            str(artifact_summary_path),
            json.dumps(saved_report_summary, ensure_ascii=False, indent=2),
        )

        official_report_md = ""
        official_report_written = False
        if review_cfg.write_official_report_default:
            official_report_dir.mkdir(parents=True, exist_ok=True)
            report_figure_manifest = {
                "figures_dir": _rel_from_official_report(artifact_bundle_figures_dir),
                "candidate_dependence": (
                    _rel_from_official_report(artifact_bundle_dir / figure_manifest["candidate_dependence"])
                    if figure_manifest["candidate_dependence"]
                    else None
                ),
                "comparison_dependence": [
                    {
                        **item,
                        "path": _rel_from_official_report(artifact_bundle_dir / item["path"]),
                    }
                    for item in figure_manifest["comparison_dependence"]
                ],
                "stability_split": (
                    _rel_from_official_report(artifact_bundle_dir / figure_manifest["stability_split"])
                    if figure_manifest["stability_split"]
                    else None
                ),
                "stability_year": (
                    _rel_from_official_report(artifact_bundle_dir / figure_manifest["stability_year"])
                    if figure_manifest["stability_year"]
                    else None
                ),
            }
            official_markdown = render_candidate_shap_full_report_markdown(
                saved_report_summary,
                figure_manifest=report_figure_manifest,
            )
            _file_gateway.write_text(str(official_report_path), official_markdown)
            official_report_md = _rel_from_project(official_report_path)
            official_report_written = True
            print(f"[report] wrote official SHAP report: {official_report_path}")

        artifact_manifest = {
            "run_id": shap_run_id,
            "run_label": review_cfg.report_run_label,
            "executed_at": report_executed_at.isoformat(),
            "artifact_path": review_cfg.artifact_path,
            "artifact_bundle_dir": _rel_from_project(artifact_bundle_dir),
            "generated_files": {
                "summary_json": _rel_from_bundle(artifact_summary_path),
                "full_report_md": _rel_from_bundle(artifact_report_path),
                "figure_manifest": figure_manifest,
            },
            "official_report": {
                "official_report_md": official_report_md,
                "written": official_report_written,
            },
        }
        _file_gateway.write_text(
            str(artifact_manifest_path),
            json.dumps(artifact_manifest, ensure_ascii=False, indent=2),
        )

        saved_output_paths = {
            "artifact_bundle_dir": _rel_from_project(artifact_bundle_dir),
            "artifact_summary_json": _rel_from_project(artifact_summary_path),
            "artifact_manifest_json": _rel_from_project(artifact_manifest_path),
            "artifact_report_md": _rel_from_project(artifact_report_path),
            "official_report_md": official_report_md,
        }

        print(f"[artifact] wrote bundle: {artifact_bundle_dir}")
        print(f"[artifact] wrote summary: {artifact_summary_path}")
        print(f"[artifact] wrote full report: {artifact_report_path}")
    return saved_output_paths, saved_report_summary


@app.cell
def _(mo, saved_output_paths):
    # セル概要: 保存した artifact / official report path を表示する。
    if not saved_output_paths:
        output_paths_view = mo.md("## 12. Saved Outputs\n\nNo files written.")
    else:
        output_paths_view = mo.vstack(
            [
                mo.md("## 12. Saved Outputs"),
                mo.md(f"- artifact bundle: `{saved_output_paths['artifact_bundle_dir']}`"),
                mo.md(f"- artifact summary: `{saved_output_paths['artifact_summary_json']}`"),
                mo.md(f"- artifact manifest: `{saved_output_paths['artifact_manifest_json']}`"),
                mo.md(f"- artifact full report: `{saved_output_paths['artifact_report_md']}`"),
                mo.md(
                    f"- official SHAP report: `{saved_output_paths['official_report_md'] or 'not written'}`"
                ),
            ]
        )
    return (output_paths_view,)


@app.cell
def _(
    candidate_summary_view,
    dependence_view,
    local_case_view,
    metrics_gate_view,
    mo,
    output_paths_view,
    redundancy_view,
    stability_view,
    verdict_view,
):
    # セル概要: 出力全体をまとめて表示する。
    final_view = mo.vstack(
        [
            metrics_gate_view,
            candidate_summary_view,
            dependence_view,
            local_case_view,
            redundancy_view,
            stability_view,
            verdict_view,
            output_paths_view,
        ]
    )
    final_view
    return


if __name__ == "__main__":
    app.run()
