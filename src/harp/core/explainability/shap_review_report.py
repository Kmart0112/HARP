from __future__ import annotations

import math
import re
from dataclasses import asdict
from typing import Any, Mapping

import pandas as pd

from .shap_review import CandidateShapReviewBundle


_TOKEN_RE = re.compile(r"[^A-Za-z0-9._-]+")


def build_shap_review_run_id(run_timestamp: str, run_label: str) -> str:
    timestamp_token = _slugify(run_timestamp) or "unknown_run"
    label_token = _slugify(run_label) or "candidate_review"
    return f"{timestamp_token}_{label_token}"


def build_shap_review_report_stem(run_date: str, run_label: str) -> str:
    date_token = _slugify(run_date) or "unknown_date"
    label_token = _slugify(run_label) or "candidate_review"
    return f"{date_token}_{label_token}_shap_report"


def build_shap_review_figure_filename(
    kind: str,
    *,
    feature_name: str | None = None,
    case_name: str | None = None,
    row_index: int | None = None,
) -> str:
    normalized_kind = _slugify(kind) or "figure"
    if normalized_kind == "dependence":
        feature_token = _slugify(feature_name)
        return f"dependence_{feature_token}.png" if feature_token else "dependence.png"
    if normalized_kind == "comparison":
        feature_token = _slugify(feature_name) or "feature"
        return f"comparison_{feature_token}.png"
    if normalized_kind == "local_case":
        case_token = _slugify(case_name) or "case"
        row_token = "row" if row_index is None else str(int(row_index))
        return f"local_case_{case_token}_{row_token}.png"
    if normalized_kind in {"beeswarm", "stability_split", "stability_year"}:
        return f"{normalized_kind}.png"
    return f"{normalized_kind}.png"


def build_candidate_shap_artifact_summary(
    *,
    review: CandidateShapReviewBundle,
    run_id: str,
    artifact_path: str,
    artifact_bundle_dir: str,
    artifact_summary_path: str,
    artifact_report_path: str,
    executed_at: str,
    report_run_label: str,
    sample_split: str,
    sample_size: int,
    held_year_range: tuple[int, int],
    split_info: Mapping[str, Any],
    figure_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    metrics_context = review.metrics_context
    verdict = review.verdict

    summary = {
        "run_id": run_id,
        "run_label": report_run_label,
        "executed_at": executed_at,
        "artifact_path": artifact_path,
        "artifact_bundle_dir": artifact_bundle_dir,
        "artifact_summary_path": artifact_summary_path,
        "artifact_report_path": artifact_report_path,
        "candidate_feature": review.candidate_summary.feature,
        "comparison_features": list(review.shap_package.comparison_features),
        "sample_split": sample_split,
        "sample_size": int(sample_size),
        "held_year_range": {
            "min": int(held_year_range[0]),
            "max": int(held_year_range[1]),
        },
        "split_info": _sanitize_json_value(dict(split_info)),
        "metrics_gate": {
            "metrics_run_label": metrics_context.metrics_run_label,
            "validation_mode": metrics_context.validation_mode,
            "delta_auc": metrics_context.delta_auc,
            "delta_logloss": metrics_context.delta_logloss,
            "delta_brier": metrics_context.delta_brier,
            "metrics_judgement": verdict.metrics_judgement,
        },
        "shap_judgement": verdict.shap_judgement,
        "final_recommendation": verdict.final_recommendation,
        "review_notes": list(verdict.review_notes),
        "candidate_summary": _sanitize_json_value(asdict(review.candidate_summary)),
        "comparison_summary": _frame_to_records(review.comparison_summary),
        "split_stability_summary": _frame_to_records(review.split_stability_summary),
        "year_stability_summary": _frame_to_records(review.year_stability_summary),
        "local_case_summary": _frame_to_records(review.local_case_summary),
        "local_case_indices": _sanitize_json_value(review.local_case_indices),
        "figure_manifest": _sanitize_json_value(dict(figure_manifest)),
    }
    return _sanitize_json_value(summary)


def render_candidate_shap_full_report_markdown(
    summary: Mapping[str, Any],
    *,
    figure_manifest: Mapping[str, Any] | None = None,
) -> str:
    figure_manifest = _as_dict(figure_manifest) or _as_dict(summary.get("figure_manifest"))
    metrics_gate = _as_dict(summary.get("metrics_gate"))
    candidate_summary = _as_dict(summary.get("candidate_summary"))
    comparison_summary = _as_list(summary.get("comparison_summary"))
    split_stability_summary = _as_list(summary.get("split_stability_summary"))
    year_stability_summary = _as_list(summary.get("year_stability_summary"))
    candidate_dependence = figure_manifest.get("candidate_dependence") or figure_manifest.get("dependence")
    comparison_dependence = _as_list(figure_manifest.get("comparison_dependence")) or _as_list(
        figure_manifest.get("comparisons")
    )

    lines = [
        "# SHAP レビュー",
        "",
        f"- run_id: `{summary.get('run_id', '')}`",
        f"- run_label: `{summary.get('run_label', '')}`",
        f"- executed_at: `{summary.get('executed_at', '')}`",
        f"- artifact_path: `{summary.get('artifact_path', '')}`",
        f"- artifact_bundle_dir: `{summary.get('artifact_bundle_dir', '')}`",
        "",
        "## 実行条件",
        f"- candidate_feature: `{summary.get('candidate_feature', '')}`",
        f"- comparison_features: `{', '.join(summary.get('comparison_features', [])) or 'None'}`",
        f"- sample_split: `{summary.get('sample_split', '')}`",
        f"- sample_size: `{summary.get('sample_size', '')}`",
        (
            f"- held_year_range: `{summary.get('held_year_range', {}).get('min', '')}`"
            f" - `{summary.get('held_year_range', {}).get('max', '')}`"
        ),
        "",
        "## Metrics Gate",
        f"- metrics_run_label: `{metrics_gate.get('metrics_run_label', '')}`",
        f"- validation_mode: `{metrics_gate.get('validation_mode', '')}`",
        f"- delta_auc: `{_fmt_number(metrics_gate.get('delta_auc'))}`",
        f"- delta_logloss: `{_fmt_number(metrics_gate.get('delta_logloss'))}`",
        f"- delta_brier: `{_fmt_number(metrics_gate.get('delta_brier'))}`",
        f"- metrics_judgement: `{metrics_gate.get('metrics_judgement', '')}`",
        "",
        "## Candidate Summary",
        f"- feature: `{candidate_summary.get('feature', '')}`",
        f"- global_rank: `{candidate_summary.get('global_rank', '')}`",
        f"- mean_abs_shap: `{_fmt_number(candidate_summary.get('mean_abs_shap'))}`",
        f"- importance_share: `{_fmt_number(candidate_summary.get('importance_share'))}`",
        f"- top_n_hit: `{candidate_summary.get('top_n_hit', '')}`",
        f"- interaction_feature: `{candidate_summary.get('interaction_feature') or 'None'}`",
        f"- outlier_share_top1pct: `{_fmt_number(candidate_summary.get('outlier_share_top1pct'))}`",
        "",
    ]

    lines.extend(
        [
            "",
            "## Candidate Dependence",
            f"- candidate: `{summary.get('candidate_feature', '')}`",
            f"- color: `{candidate_summary.get('interaction_feature') or 'None'}`",
            "",
        ]
    )
    lines.extend(_render_image_block("Candidate dependence", candidate_dependence))

    lines.extend(["", "## Comparison Dependence"])
    if not comparison_summary:
        lines.append("- comparison_summary: none")
    else:
        for row in comparison_summary:
            lines.append(
                "- "
                + ", ".join(
                    [
                        f"feature=`{row.get('feature', '')}`",
                        f"global_rank=`{row.get('global_rank', '')}`",
                        f"mean_abs_shap=`{_fmt_number(row.get('mean_abs_shap'))}`",
                        f"candidate_shap_corr=`{_fmt_number(row.get('candidate_shap_corr'))}`",
                        f"feature_value_corr=`{_fmt_number(row.get('feature_value_corr'))}`",
                        f"redundancy_flag=`{row.get('redundancy_flag', '')}`",
                    ]
                )
            )
    for item in comparison_dependence:
        feature_name = item.get("feature", "")
        lines.extend(["", f"### comparison: `{feature_name}`", ""])
        lines.extend(_render_image_block(f"Comparison dependence {feature_name}", item.get("path")))

    lines.extend(["", "## Split / Year Change"])
    if split_stability_summary:
        lines.append("### Split change")
        for row in split_stability_summary:
            lines.append(
                "- "
                + ", ".join(
                    [
                        f"split=`{row.get('split', '')}`",
                        f"rows=`{row.get('rows', '')}`",
                        f"candidate_mean_abs_shap=`{_fmt_number(row.get('candidate_mean_abs_shap'))}`",
                        f"candidate_rank=`{row.get('candidate_rank', '')}`",
                    ]
                )
            )
    lines.extend(_render_image_block("Split stability", figure_manifest.get("stability_split")))

    if year_stability_summary:
        lines.extend(["", "### Year change"])
        for row in year_stability_summary:
            lines.append(
                "- "
                + ", ".join(
                    [
                        f"held_year=`{row.get('held_year', '')}`",
                        f"rows=`{row.get('rows', '')}`",
                        f"candidate_mean_abs_shap=`{_fmt_number(row.get('candidate_mean_abs_shap'))}`",
                        f"candidate_rank=`{row.get('candidate_rank', '')}`",
                    ]
                )
            )
    lines.extend(_render_image_block("Year stability", figure_manifest.get("stability_year")))

    lines.extend(
        [
            "",
            "## 結論",
            f"- shap_judgement: `{summary.get('shap_judgement', '')}`",
            f"- final_recommendation: `{summary.get('final_recommendation', '')}`",
            "",
            "### Review Notes",
        ]
    )
    for note in _as_list(summary.get("review_notes")):
        lines.append(f"- {note}")

    lines.extend(
        [
            "",
            "## Artifact 参照",
            f"- artifact_bundle_dir: `{summary.get('artifact_bundle_dir', '')}`",
            f"- artifact_summary_path: `{summary.get('artifact_summary_path', '')}`",
            f"- artifact_report_path: `{summary.get('artifact_report_path', '')}`",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _frame_to_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return _sanitize_json_value(frame.to_dict(orient="records"))


def _sanitize_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_json_value(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item") and callable(value.item):
        try:
            return _sanitize_json_value(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return str(value)


def _slugify(value: str | None) -> str:
    text = str(value or "").strip().replace("/", "_")
    text = _TOKEN_RE.sub("_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("._")


def _fmt_number(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(number) or math.isinf(number):
        return ""
    return f"{number:.6f}"


def _render_image_block(alt: str, path: Any) -> list[str]:
    if not path:
        return []
    return [f"![{alt}]({path})"]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
