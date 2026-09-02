from __future__ import annotations

import csv
import io
import os
from pathlib import Path

from harp.core.feature_validation_report import (
    FeatureValidationReportModel,
    FeatureValidationReportScenarioResult,
    FeatureValidationReportScenarioSpec,
    build_feature_validation_report_model,
)

from .dto import FeatureValidationRequest, ValidationScenarioResult, ValidationScenarioSpec


def render_runs_csv(scenario_results: list[ValidationScenarioResult]) -> str:
    rows = [_build_csv_row(result) for result in scenario_results]
    headers = [
        "scenario",
        "scenario_run_id",
        "enabled_features",
        "enabled_cat_features",
        "features_config_path",
        "timestamp",
        "auc",
        "logloss",
        "brier",
        "delta_auc",
        "delta_logloss",
        "delta_brier",
        "metrics_judgement",
        "shap_judgement",
        "shap_report",
        "decision",
    ]
    buffer = io.StringIO()
    with buffer:
        writer = csv.DictWriter(buffer, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue()


def build_report_model(
    *,
    req: FeatureValidationRequest,
    scenario_results: tuple[ValidationScenarioResult, ...],
) -> FeatureValidationReportModel:
    return build_feature_validation_report_model(
        target_features=tuple(feature.feature_name for feature in req.report_spec.target_features),
        scenarios=tuple(_to_report_scenario_spec(scenario) for scenario in req.scenarios),
        scenario_results=tuple(_to_report_scenario_result(result) for result in scenario_results),
        baseline_scenario_name=req.scenarios[0].scenario_name,
        finalize=req.finalize,
        final_selected_scenario=req.final_selected_scenario,
    )


def render_report_markdown(
    *,
    req: FeatureValidationRequest,
    report_model: FeatureValidationReportModel,
    parent_run_id: str,
    theme_revision: int,
    append_history: tuple[str, ...],
    report_out: str,
    runs_csv_out: str,
    run_log_dir: str,
    scenario_results: tuple[ValidationScenarioResult, ...],
) -> str:
    spec = req.report_spec
    baseline = next(result for result in scenario_results if result.scenario_name == req.scenarios[0].scenario_name)
    feature_verdicts = report_model.feature_verdict_by_name

    lines = [
        f"# {spec.title}",
        "",
        "## 0. 実行情報",
        f"- 実行名: {req.validation_name}",
        f"- 区分: {req.category}",
        f"- テーマリビジョン: {theme_revision}",
        f"- 評価ノートブック: `{spec.metrics_notebook_path}`",
        f"- SHAP ノートブック: `{spec.shap_notebook_path}`",
        f"- 実験結果CSV: `{runs_csv_out}`",
        f"- 実行ログ: `{run_log_dir}`",
        "",
        "## 1. 目的",
        f"- 背景: {spec.background}",
        "- 仮説:",
        *[f"  - {line}" for line in spec.hypothesis_lines],
        "",
        "## 2. リークチェック（事前確認）",
        *[f"- {line}" for line in spec.leakage_notes],
        "",
        "## 3. 変更一覧（特徴量定義サマリ）",
        "| 特徴量名 | 種別 | 変更種別 | 作り方/意味の1行要約 | 判定 |",
        "|---|---|---|---|---|",
    ]
    for feature in spec.target_features:
        lines.append(
            f"| `{feature.feature_name}` | {feature.feature_type} | {feature.change_type} | "
            f"{feature.summary} | {feature_verdicts[feature.feature_name]} |"
        )

    lines.extend(["", "## 4. 特徴量詳細"])
    for idx, feature in enumerate(spec.target_features, start=1):
        lines.extend(
            [
                f"### 4.{idx} `{feature.feature_name}`",
                f"- 作り方: `{feature.final_column}` を特徴量として利用する。",
                f"- 意味: {feature.summary}",
                "- 実装反映先:",
                f"  - dbtモデル: `{feature.dbt_model_path}`",
                f"  - model YAML: `{feature.dbt_yaml_path}`",
                f"  - 最終列: `{feature.final_column}`",
                (
                    f"- 重複比較対象: `{', '.join(feature.comparison_features)}`"
                    if feature.comparison_features
                    else "- 重複比較対象: なし"
                ),
                "",
            ]
        )

    lines.extend(
        [
            "## 5. 実行条件",
            f"- 実行コマンド: `{req.command}`",
            *[f"- {note}" for note in spec.implementation_notes],
            "",
            "## 6. 検証結果",
            "### 6.1 ベースライン",
            "| run | AUC | LogLoss | Brier |",
            "|---|---:|---:|---:|",
            (
                f"| {baseline.scenario_name} | {baseline.metrics_run.auc:.9f} | "
                f"{baseline.metrics_run.logloss:.9f} | {baseline.metrics_run.brier:.9f} |"
            ),
            "",
            "### 6.2 シナリオ比較",
            "| run | AUC | LogLoss | Brier | DeltaAUC | DeltaLogLoss | DeltaBrier | Metrics判定 | SHAP判定 | 判定 |",
            "|---|---:|---:|---:|---:|---:|---:|---|---|---|",
        ]
    )
    for result in scenario_results[1:]:
        shap_judgement = "-" if result.shap_review is None else result.shap_review.shap_judgement
        lines.append(
            f"| {result.scenario_name} | {result.metrics_run.auc:.9f} | {result.metrics_run.logloss:.9f} | "
            f"{result.metrics_run.brier:.9f} | {result.delta_auc:+.9f} | {result.delta_logloss:+.9f} | "
            f"{result.delta_brier:+.9f} | {result.metrics_judgement} | {shap_judgement} | {result.decision} |"
        )

    lines.extend(["", "### 6.5 SHAP レビュー（必須）"])
    for result in scenario_results:
        if result.shap_review is None:
            continue
        scenario = _find_scenario_spec_by_name(req.scenarios, result.scenario_name)
        comparison_features = () if scenario is None or scenario.shap_request is None else scenario.shap_request.comparison_features
        dependence_image_markdown = _render_dependence_image_markdown(
            report_path=report_out,
            dependence_path=result.shap_review.candidate_dependence_path,
            dependence_source_path=result.shap_review.candidate_dependence_source_path,
            candidate_feature=result.shap_review.candidate_feature,
        )
        lines.extend(
            [
                f"#### `{result.shap_review.candidate_feature}`",
                f"- metrics_judgement: `{result.shap_review.metrics_judgement}`",
                f"- shap_judgement: `{result.shap_review.shap_judgement}`",
                "- candidate global importance:",
                f"  - global rank: `{result.shap_review.global_rank}`",
                f"  - mean_abs_shap: `{result.shap_review.mean_abs_shap}`",
                f"  - importance_share: `{result.shap_review.importance_share}`",
                (
                    f"- comparison dependence reviewed as set: `{', '.join(comparison_features)}`"
                    if comparison_features
                    else "- comparison dependence reviewed as set: なし"
                ),
                "- candidate dependence:",
                dependence_image_markdown,
                f"- dependence の形の考察: {_build_dependence_consideration(result, comparison_features)}",
                f"- shap_report_path: `{result.shap_review.official_report_path}`",
                "",
            ]
        )

    lines.extend(["", "## 6.6 追実験メモ"])
    if append_history:
        lines.extend([f"- {note}" for note in append_history])
    else:
        lines.append("- なし")

    lines.extend(
        [
            "## 7. 最終判定",
            f"- 判定: {report_model.decision}",
            (
                f"- 最終採用シナリオ: `{report_model.final_selected_scenario}`"
                if report_model.final_selected_scenario
                else "- 最終採用シナリオ: なし"
            ),
            f"- 採用セット（最終）: {_render_feature_list(report_model.adopted_features)}",
            f"- 保留セット: {_render_feature_list(report_model.held_features)}",
            f"- 不採用セット: {_render_feature_list(report_model.rejected_features)}",
            "",
            "## 8. 推奨反映内容",
            f"- validation 実行中は source registry `{req.features_config_path}` を変更していない。",
            "- scenario ごとの一時 config を使って比較している。",
            "- `採用` の場合は、review 後に registry の `status: on` へ反映する。",
            "- contracts は必要に応じて `uv run python -m pipeline.jobs.export_feature_contract` で registry から再生成する。",
            f"- 推奨 ON: {_render_feature_list(report_model.adopted_features)}",
            f"- 推奨 OFF: {_render_feature_list(report_model.rejected_features)}",
            "",
            "## 9. MLflow 紐付け情報",
            f"- mlflow_experiment_name: `{req.experiment_name}`",
            f"- mlflow_run_id: `{parent_run_id}`",
            f"- report_path: `{report_out}`",
            f"- runs_csv_path: `{runs_csv_out}`",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def build_parent_summary(
    *,
    req: FeatureValidationRequest,
    report_model: FeatureValidationReportModel,
    parent_run_id: str,
    scenario_results: list[ValidationScenarioResult],
    theme_status: str,
    theme_revision: int,
    report_out: str,
    runs_csv_out: str,
    run_log_dir: str,
    append_history: tuple[str, ...],
) -> dict[str, object]:
    return {
        "validation_name": req.validation_name,
        "category": req.category,
        "change_summary": req.change_summary,
        "mlflow_experiment_name": req.experiment_name,
        "mlflow_run_id": parent_run_id,
        "theme_status": theme_status,
        "theme_revision": theme_revision,
        "preset_name": req.preset_name,
        "command": req.command,
        "git_commit": req.git_commit,
        "report_path": report_out,
        "runs_csv_path": runs_csv_out,
        "run_log_dir": run_log_dir,
        "decision": report_model.decision,
        "final_selected_scenario": report_model.final_selected_scenario,
        "final_selected_features": list(report_model.final_selected_features),
        "scenario_run_ids": {result.scenario_name: result.scenario_run_id for result in scenario_results},
        "append_history": list(append_history),
        "scenarios": [
            build_shap_summary(result, attempt_number=index)
            for index, result in enumerate(scenario_results, start=1)
        ],
        "restored_features_state": f"source registry untouched: {req.features_config_path}",
    }


def build_shap_summary(result: ValidationScenarioResult, *, attempt_number: int) -> dict[str, object]:
    review = result.shap_review
    payload = build_scenario_summary(result, attempt_number=attempt_number)
    if review is None:
        return payload
    payload.update(
        {
            "candidate_feature": review.candidate_feature,
            "shap_metrics_judgement": review.metrics_judgement,
            "shap_judgement": review.shap_judgement,
            "final_recommendation": review.final_recommendation,
            "official_report_path": review.official_report_path,
            "official_report_source_path": review.official_report_source_path,
            "summary_json_path": review.summary_json_path,
            "manifest_json_path": review.manifest_json_path,
            "artifact_bundle_dir": review.artifact_bundle_dir,
            "artifact_report_path": review.artifact_report_path,
            "candidate_dependence_path": review.candidate_dependence_path,
            "candidate_dependence_source_path": review.candidate_dependence_source_path,
            "global_rank": review.global_rank,
            "mean_abs_shap": review.mean_abs_shap,
            "importance_share": review.importance_share,
            "shap_log_path": review.log_path,
            "artifact_paths": list(review.artifact_paths),
        }
    )
    return payload


def build_scenario_summary(result: ValidationScenarioResult, *, attempt_number: int) -> dict[str, object]:
    return {
        "scenario_run_id": result.scenario_run_id,
        "scenario_name": result.scenario_name,
        "scenario_attempt": attempt_number,
        "enabled_features": list(result.enabled_features),
        "enabled_cat_features": list(result.enabled_cat_features),
        "features_config_path": result.features_config_path,
        "timestamp": result.metrics_run.timestamp,
        "auc": result.metrics_run.auc,
        "logloss": result.metrics_run.logloss,
        "brier": result.metrics_run.brier,
        "delta_auc": result.delta_auc,
        "delta_logloss": result.delta_logloss,
        "delta_brier": result.delta_brier,
        "metrics_judgement": result.metrics_judgement,
        "decision": result.decision,
        "artifact_path": result.metrics_run.artifact_path,
        "manifest_path": result.metrics_run.manifest_path,
        "metrics_log_path": result.metrics_run.log_path,
        "artifact_paths": list(result.metrics_run.artifact_paths),
    }


def _build_csv_row(result: ValidationScenarioResult) -> dict[str, str]:
    shap_review = result.shap_review
    return {
        "scenario": result.scenario_name,
        "scenario_run_id": result.scenario_run_id,
        "enabled_features": "|".join(result.enabled_features),
        "enabled_cat_features": "|".join(result.enabled_cat_features),
        "features_config_path": result.features_config_path,
        "timestamp": result.metrics_run.timestamp,
        "auc": f"{result.metrics_run.auc:.9f}",
        "logloss": f"{result.metrics_run.logloss:.9f}",
        "brier": f"{result.metrics_run.brier:.9f}",
        "delta_auc": f"{result.delta_auc:+.9f}",
        "delta_logloss": f"{result.delta_logloss:+.9f}",
        "delta_brier": f"{result.delta_brier:+.9f}",
        "metrics_judgement": result.metrics_judgement,
        "shap_judgement": "" if shap_review is None else shap_review.shap_judgement,
        "shap_report": "" if shap_review is None else shap_review.official_report_path,
        "decision": result.decision,
    }


def _to_report_scenario_spec(scenario: ValidationScenarioSpec) -> FeatureValidationReportScenarioSpec:
    return FeatureValidationReportScenarioSpec(
        scenario_name=scenario.scenario_name,
        validation_mode=scenario.validation_mode,
        candidate_feature="" if scenario.shap_request is None else scenario.shap_request.candidate_feature,
        enabled_toggle_features=tuple(toggle.feature_name for toggle in scenario.toggles if toggle.enabled),
    )


def _to_report_scenario_result(result: ValidationScenarioResult) -> FeatureValidationReportScenarioResult:
    return FeatureValidationReportScenarioResult(
        scenario_name=result.scenario_name,
        enabled_features=result.enabled_features,
        decision=result.decision,
    )


def _render_feature_list(features: tuple[str, ...]) -> str:
    if not features:
        return "なし"
    return ", ".join(f"`{feature}`" for feature in features)


def _find_scenario_spec_by_name(
    scenarios: tuple[ValidationScenarioSpec, ...],
    scenario_name: str,
) -> ValidationScenarioSpec | None:
    return next((scenario for scenario in scenarios if scenario.scenario_name == scenario_name), None)


def _build_dependence_consideration(
    result: ValidationScenarioResult,
    comparison_features: tuple[str, ...],
) -> str:
    if result.shap_review is None:
        return "SHAP review not available."

    scope_text = (
        f"関連特徴セット `{', '.join(comparison_features)}` との comparison dependence も確認済み。"
        if comparison_features
        else "candidate 単独の dependence を確認済み。"
    )
    judgement_text = {
        "問題なし": "大きなリーク・外れ値依存の懸念は見当たらない。",
        "注意": "比較特徴との冗長性または安定性には注意が必要。",
        "リーク懸念あり": "寄与集中が強く、リークまたは外れ値依存の疑いがある。",
    }.get(result.shap_review.shap_judgement, f"SHAP 判定 `{result.shap_review.shap_judgement}` を確認。")
    rank_text = f"global rank は `{result.shap_review.global_rank}`。"
    return f"自動所見: {scope_text} {judgement_text} {rank_text}".strip()


def _render_dependence_image_markdown(
    *,
    report_path: str,
    dependence_path: str,
    dependence_source_path: str,
    candidate_feature: str,
) -> str:
    if not dependence_path.strip() or not dependence_source_path.strip():
        return "- dependence image: not available"

    markdown_path = _build_report_relative_path(report_path=report_path, target_path=dependence_path)
    return f"![Candidate dependence: {candidate_feature}]({markdown_path})"


def _build_report_relative_path(*, report_path: str, target_path: str) -> str:
    report_dir = _as_absolute_path(report_path).parent
    target = _as_absolute_path(target_path)
    return Path(os.path.relpath(target, start=report_dir)).as_posix()


def _as_absolute_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return Path.cwd() / candidate
