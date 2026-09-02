from __future__ import annotations

import csv
import io

from .dto import (
    FeatureSelectionDecisionRow,
    FeatureSelectionRequest,
    FeatureSelectionScenarioResult,
)


def render_runs_csv(results: tuple[FeatureSelectionScenarioResult, ...]) -> str:
    headers = [
        "scenario",
        "scenario_run_id",
        "phase",
        "group_id",
        "tested_set",
        "enabled_features",
        "timestamp",
        "auc",
        "logloss",
        "brier",
        "delta_auc",
        "delta_logloss",
        "delta_brier",
        "metrics_judgement",
    ]
    buffer = io.StringIO()
    with buffer:
        writer = csv.DictWriter(buffer, fieldnames=headers)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "scenario": result.scenario_name,
                    "scenario_run_id": result.scenario_run_id,
                    "phase": result.phase,
                    "group_id": "" if result.group_id is None else result.group_id,
                    "tested_set": result.tested_set,
                    "enabled_features": "|".join(result.enabled_features),
                    "timestamp": result.metrics_run.timestamp,
                    "auc": f"{result.metrics_run.auc:.9f}",
                    "logloss": f"{result.metrics_run.logloss:.9f}",
                    "brier": f"{result.metrics_run.brier:.9f}",
                    "delta_auc": f"{result.delta_auc:+.9f}",
                    "delta_logloss": f"{result.delta_logloss:+.9f}",
                    "delta_brier": f"{result.delta_brier:+.9f}",
                    "metrics_judgement": result.metrics_judgement,
                }
            )
        return buffer.getvalue()


def render_decisions_csv(rows: tuple[FeatureSelectionDecisionRow, ...]) -> str:
    headers = [
        "group_id",
        "decision_type",
        "winner_set",
        "loser_sets",
        "reason",
        "delta_auc",
        "delta_logloss",
        "delta_brier",
    ]
    buffer = io.StringIO()
    with buffer:
        writer = csv.DictWriter(buffer, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "group_id": row.group_id,
                    "decision_type": row.decision_type,
                    "winner_set": row.winner_set,
                    "loser_sets": "|".join(row.loser_sets),
                    "reason": row.reason,
                    "delta_auc": "" if row.delta_auc is None else f"{row.delta_auc:+.9f}",
                    "delta_logloss": "" if row.delta_logloss is None else f"{row.delta_logloss:+.9f}",
                    "delta_brier": "" if row.delta_brier is None else f"{row.delta_brier:+.9f}",
                }
            )
        return buffer.getvalue()


def render_report_markdown(
    *,
    req: FeatureSelectionRequest,
    parent_run_id: str,
    theme_revision: int,
    append_history: tuple[str, ...],
    report_out: str,
    runs_csv_out: str,
    decisions_csv_out: str,
    selected_contract_snapshot_out: str,
    target_contract_path: str,
    contract_written: bool,
    scenario_results: tuple[FeatureSelectionScenarioResult, ...],
    decision_rows: tuple[FeatureSelectionDecisionRow, ...],
    base_feature_names: list[str],
    final_feature_names: list[str],
    auc_threshold: float,
    logloss_threshold: float,
) -> str:
    spec = req.report_spec
    aggregate_rows = [row for row in decision_rows if row.decision_type == "aggregate"]
    variant_rows = [row for row in decision_rows if row.decision_type == "variant"]
    unresolved = [row for row in decision_rows if row.unresolved]
    added_features = [feature for feature in final_feature_names if feature not in set(base_feature_names)]
    removed_features = [feature for feature in base_feature_names if feature not in set(final_feature_names)]
    lines = [
        f"# {spec.title}",
        "",
        "## 0. 実行情報",
        f"- 実行名: {req.validation_name}",
        f"- 区分: {req.category}",
        f"- テーマリビジョン: {theme_revision}",
        f"- base_feature_set_name: `{req.base_feature_set_name}`",
        f"- target_contract_path: `{target_contract_path}`",
        f"- selected_contract_snapshot: `{selected_contract_snapshot_out}`",
        f"- runs_csv_path: `{runs_csv_out}`",
        f"- decisions_csv_path: `{decisions_csv_out}`",
        "",
        "## 1. 目的",
        f"- 背景: {spec.background}",
        "- 仮説:",
        *[f"  - {line}" for line in spec.hypothesis_lines],
        "",
        "## 2. リークチェック（事前確認）",
        *[f"- {line}" for line in spec.leakage_notes],
        "",
        "## 3. 実行条件",
        f"- 実行コマンド: `{req.command}`",
        f"- AUC threshold: `{auc_threshold}`",
        f"- LogLoss threshold: `{logloss_threshold}`",
        *[f"- {line}" for line in spec.implementation_notes],
        "",
        "## 4. Aggregate 判定",
        "| group_id | winner_set | loser_sets | reason | delta_auc | delta_logloss | delta_brier |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for row in aggregate_rows:
        lines.append(
            f"| {row.group_id} | {row.winner_set or '-'} | {' / '.join(row.loser_sets) or '-'} | {row.reason} | "
            f"{'-' if row.delta_auc is None else f'{row.delta_auc:+.9f}'} | "
            f"{'-' if row.delta_logloss is None else f'{row.delta_logloss:+.9f}'} | "
            f"{'-' if row.delta_brier is None else f'{row.delta_brier:+.9f}'} |"
        )

    lines.extend(
        [
            "",
            "## 5. Variant 判定",
            "| group_id | winner_set | loser_sets | reason | delta_auc | delta_logloss | delta_brier |",
            "|---|---|---|---|---:|---:|---:|",
        ]
    )
    for row in variant_rows:
        lines.append(
            f"| {row.group_id} | {row.winner_set or '-'} | {' / '.join(row.loser_sets) or '-'} | {row.reason} | "
            f"{'-' if row.delta_auc is None else f'{row.delta_auc:+.9f}'} | "
            f"{'-' if row.delta_logloss is None else f'{row.delta_logloss:+.9f}'} | "
            f"{'-' if row.delta_brier is None else f'{row.delta_brier:+.9f}'} |"
        )

    lines.extend(["", "## 6. unresolved groups"])
    if unresolved:
        lines.extend([f"- `{row.group_id}`: {row.reason}" for row in unresolved])
    else:
        lines.append("- なし")

    lines.extend(["", "## 6.5 追実験メモ"])
    if append_history:
        lines.extend([f"- {note}" for note in append_history])
    else:
        lines.append("- なし")

    lines.extend(
        [
            "",
            "## 7. 最終 feature set 反映",
            f"- 追加: {', '.join(f'`{feature}`' for feature in added_features) if added_features else 'なし'}",
            f"- 削除: {', '.join(f'`{feature}`' for feature in removed_features) if removed_features else 'なし'}",
            f"- selected_contract_snapshot_path: `{selected_contract_snapshot_out}`",
            f"- contract_written: `{str(contract_written).lower()}`",
            "",
            "## 8. scenario metrics",
            "| scenario | phase | group_id | tested_set | delta_auc | delta_logloss | delta_brier | metrics_judgement |",
            "|---|---|---|---|---:|---:|---:|---|",
        ]
    )
    for result in scenario_results:
        lines.append(
            f"| {result.scenario_name} | {result.phase} | {result.group_id or '-'} | {result.tested_set} | "
            f"{result.delta_auc:+.9f} | {result.delta_logloss:+.9f} | {result.delta_brier:+.9f} | {result.metrics_judgement} |"
        )

    lines.extend(
        [
            "",
            "## 9. MLflow 紐付け情報",
            f"- mlflow_experiment_name: `{req.experiment_name}`",
            f"- mlflow_run_id: `{parent_run_id}`",
            f"- report_path: `{report_out}`",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def build_parent_summary(
    *,
    req: FeatureSelectionRequest,
    parent_run_id: str,
    theme_status: str,
    theme_revision: int,
    report_out: str,
    runs_csv_out: str,
    decisions_csv_out: str,
    selected_contract_snapshot_out: str,
    target_contract_path: str,
    run_log_dir: str,
    append_history: tuple[str, ...],
    scenario_results: tuple[FeatureSelectionScenarioResult, ...],
    decision_rows: tuple[FeatureSelectionDecisionRow, ...],
    final_feature_names: list[str],
    final_cat_features: list[str],
    contract_written: bool,
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
        "decisions_csv_path": decisions_csv_out,
        "selected_contract_snapshot_path": selected_contract_snapshot_out,
        "target_contract_path": target_contract_path,
        "run_log_dir": run_log_dir,
        "append_history": list(append_history),
        "contract_written": contract_written,
        "scenario_run_ids": {result.scenario_name: result.scenario_run_id for result in scenario_results},
        "scenarios": [
            build_scenario_summary(result, attempt_number=index)
            for index, result in enumerate(scenario_results, start=1)
        ],
        "decisions": [
            {
                "group_id": row.group_id,
                "decision_type": row.decision_type,
                "winner_set": row.winner_set,
                "loser_sets": list(row.loser_sets),
                "reason": row.reason,
                "delta_auc": row.delta_auc,
                "delta_logloss": row.delta_logloss,
                "delta_brier": row.delta_brier,
                "unresolved": row.unresolved,
            }
            for row in decision_rows
        ],
        "final_feature_names": final_feature_names,
        "final_cat_features": final_cat_features,
    }


def build_scenario_summary(result: FeatureSelectionScenarioResult, *, attempt_number: int) -> dict[str, object]:
    return {
        "scenario_run_id": result.scenario_run_id,
        "scenario_name": result.scenario_name,
        "scenario_attempt": attempt_number,
        "phase": result.phase,
        "group_id": result.group_id,
        "tested_set": result.tested_set,
        "enabled_features": list(result.enabled_features),
        "timestamp": result.metrics_run.timestamp,
        "auc": result.metrics_run.auc,
        "logloss": result.metrics_run.logloss,
        "brier": result.metrics_run.brier,
        "delta_auc": result.delta_auc,
        "delta_logloss": result.delta_logloss,
        "delta_brier": result.delta_brier,
        "metrics_judgement": result.metrics_judgement,
        "artifact_path": result.metrics_run.artifact_path,
        "manifest_path": result.metrics_run.manifest_path,
        "metrics_log_path": result.metrics_run.log_path,
        "artifact_paths": list(result.metrics_run.artifact_paths),
    }
