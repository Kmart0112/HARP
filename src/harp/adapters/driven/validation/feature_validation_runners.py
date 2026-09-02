from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from harp.interface.ports.validation_runner_ports import MetricsRunResult, ShapReviewResult


class MarimoFeatureValidationMetricsRunnerAdapter:
    def __init__(self, *, project_root: str) -> None:
        self._project_root = Path(project_root)
        self._notebook_path = self._project_root / "notebook" / "prd" / "lgbm_fuku_platt_metrics.py"
        self._artifact_root = self._project_root / "notebook" / "prd" / "outputs" / "artifacts"
        self._metadata_root = self._project_root / "notebook" / "prd" / "outputs" / "metadata"

    def run_metrics(
        self,
        *,
        scenario_name: str,
        run_log_dir: str,
        features_config_path: str,
    ) -> MetricsRunResult:
        safe_name = _safe_token(scenario_name)
        run_token = _safe_token(Path(run_log_dir).name)
        artifact_path = self._artifact_root / "feature_validation" / run_token / safe_name / f"{safe_name}.pkl"
        manifest_path = self._metadata_root / "feature_validation" / run_token / safe_name / f"{safe_name}.json"
        log_path = Path(run_log_dir) / "logs" / f"{safe_name}_metrics.log"

        cmd = [
            "uv",
            "run",
            "python",
            str(self._notebook_path.relative_to(self._project_root)),
            "--resolved-features-config-path",
            str(features_config_path),
            "--artifact-path",
            str(artifact_path),
            "--manifest-path",
            str(manifest_path),
        ]
        proc = subprocess.run(
            cmd,
            cwd=self._project_root,
            text=True,
            capture_output=True,
            env=os.environ.copy(),
        )
        _write_log(log_path, proc.stdout, proc.stderr)
        if proc.returncode != 0:
            raise RuntimeError(f"metrics notebook failed: scenario={scenario_name} log={log_path}")
        if not manifest_path.exists():
            raise FileNotFoundError(f"metrics manifest not found: {manifest_path}")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        metrics = manifest.get("metrics")
        if not isinstance(metrics, dict):
            raise KeyError(f"metrics missing in manifest: {manifest_path}")

        timestamp = datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()
        return MetricsRunResult(
            scenario_name=scenario_name,
            timestamp=timestamp,
            auc=float(metrics["auc"]),
            logloss=float(metrics["logloss"]),
            brier=float(metrics["brier"]),
            artifact_path=str(artifact_path),
            manifest_path=str(manifest_path),
            log_path=str(log_path),
            artifact_paths=(str(artifact_path), str(manifest_path)),
        )


class MarimoFeatureValidationShapRunnerAdapter:
    def __init__(self, *, project_root: str) -> None:
        self._project_root = Path(project_root)
        self._notebook_path = self._project_root / "notebook" / "lab" / "lgbm_fuku_platt_shap.py"

    def run_shap_review(
        self,
        *,
        scenario_name: str,
        artifact_path: str,
        candidate_feature: str,
        comparison_features: tuple[str, ...],
        validation_mode: str,
        metrics_run_label: str,
        report_run_label: str,
        delta_auc: float,
        delta_logloss: float,
        delta_brier: float,
        run_log_dir: str,
    ) -> ShapReviewResult:
        safe_name = _safe_token(scenario_name)
        artifact_root_dir = Path(run_log_dir) / "shap_artifacts" / safe_name
        log_path = Path(run_log_dir) / "logs" / f"{safe_name}_shap.log"
        if artifact_root_dir.exists():
            shutil.rmtree(artifact_root_dir)
        cmd = [
            "uv",
            "run",
            "python",
            str(self._notebook_path.relative_to(self._project_root)),
            "--artifact-path",
            str(artifact_path),
            "--candidate-feature",
            candidate_feature,
            "--validation-mode",
            validation_mode,
            "--metrics-run-label",
            metrics_run_label,
            "--report-run-label",
            report_run_label,
            "--delta-auc",
            str(delta_auc),
            "--delta-logloss",
            str(delta_logloss),
            "--delta-brier",
            str(delta_brier),
            "--artifact-root-dir",
            str(artifact_root_dir),
        ]
        for idx, feature in enumerate(comparison_features, start=1):
            cmd.extend([f"--comparison-feature-{idx}", feature])

        proc = subprocess.run(
            cmd,
            cwd=self._project_root,
            text=True,
            capture_output=True,
            env=os.environ.copy(),
        )
        _write_log(log_path, proc.stdout, proc.stderr)
        if proc.returncode != 0:
            raise RuntimeError(f"shap notebook failed: scenario={scenario_name} log={log_path}")

        summary_path = _single_file(artifact_root_dir, "summary.json")
        manifest_path = _single_file(artifact_root_dir, "manifest.json")
        full_report_path = _single_file(artifact_root_dir, "full_report.md")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        candidate_summary = summary.get("candidate_summary")
        metrics_gate = summary.get("metrics_gate")
        if not isinstance(candidate_summary, dict) or not isinstance(metrics_gate, dict):
            raise KeyError(f"summary schema invalid: {summary_path}")

        candidate_dependence_source_path = _resolve_candidate_dependence_source_path(
            project_root=self._project_root,
            summary=summary,
            manifest=manifest,
            bundle_dir=summary_path.parent,
        )
        candidate_dependence_path = (
            ""
            if candidate_dependence_source_path is None
            else str(candidate_dependence_source_path.relative_to(self._project_root))
        )

        official_report_source_path = _resolve_official_report_source_path(
            project_root=self._project_root,
            manifest_path=manifest_path,
            report_run_label=report_run_label,
        )
        if not official_report_source_path.exists():
            raise FileNotFoundError(f"official SHAP report not found: {official_report_source_path}")
        official_report_path = str(official_report_source_path.relative_to(self._project_root))

        artifact_paths = tuple(
            str(path)
            for path in sorted(
                {
                    summary_path,
                    manifest_path,
                    full_report_path,
                    official_report_source_path,
                    *artifact_root_dir.rglob("*"),
                },
                key=lambda path: str(path),
            )
            if path.is_file()
        )
        return ShapReviewResult(
            scenario_name=scenario_name,
            candidate_feature=candidate_feature,
            metrics_judgement=str(metrics_gate["metrics_judgement"]),
            shap_judgement=str(summary["shap_judgement"]),
            final_recommendation=str(summary["final_recommendation"]),
            official_report_path=official_report_path,
            official_report_source_path=str(official_report_source_path),
            summary_json_path=str(summary_path),
            manifest_json_path=str(manifest_path),
            artifact_bundle_dir=str(artifact_root_dir),
            artifact_report_path=str(full_report_path),
            candidate_dependence_path=candidate_dependence_path,
            candidate_dependence_source_path=(
                "" if candidate_dependence_source_path is None else str(candidate_dependence_source_path)
            ),
            global_rank=str(candidate_summary["global_rank"]),
            mean_abs_shap=str(candidate_summary["mean_abs_shap"]),
            importance_share=str(candidate_summary["importance_share"]),
            log_path=str(log_path),
            artifact_paths=artifact_paths,
        )


def _write_log(path: Path, stdout: str, stderr: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{stdout}\n\n[stderr]\n{stderr}", encoding="utf-8")


def _single_file(root_dir: Path, file_name: str) -> Path:
    matches = sorted(root_dir.rglob(file_name))
    if len(matches) != 1:
        raise FileNotFoundError(f"expected one {file_name} under {root_dir}, found={len(matches)}")
    return matches[0]


def _resolve_official_report_source_path(
    *,
    project_root: Path,
    manifest_path: Path,
    report_run_label: str,
) -> Path:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    official_report = manifest.get("official_report")
    if isinstance(official_report, dict):
        rel_path = official_report.get("official_report_md")
        if isinstance(rel_path, str) and rel_path.strip():
            return project_root / rel_path

    report_dir = project_root / "notebook" / "report" / "shap"
    matches = sorted(report_dir.glob(f"*_{report_run_label}_shap_report.md"), key=lambda path: path.stat().st_mtime)
    if matches:
        return matches[-1]
    raise FileNotFoundError(f"official SHAP report path missing in manifest: {manifest_path}")


def _resolve_candidate_dependence_source_path(
    *,
    project_root: Path,
    summary: dict[str, object],
    manifest: dict[str, object],
    bundle_dir: Path,
) -> Path | None:
    rel_path = _extract_dependence_rel_path(summary.get("figure_manifest"))
    if rel_path is None:
        generated_files = manifest.get("generated_files")
        figure_manifest = generated_files.get("figure_manifest") if isinstance(generated_files, dict) else None
        rel_path = _extract_dependence_rel_path(figure_manifest)
    if rel_path is None:
        return None

    candidate = bundle_dir / rel_path
    if candidate.exists():
        return candidate.resolve()

    project_candidate = project_root / rel_path
    if project_candidate.exists():
        return project_candidate.resolve()
    return None


def _extract_dependence_rel_path(figure_manifest: object) -> str | None:
    if not isinstance(figure_manifest, dict):
        return None
    rel_path = figure_manifest.get("candidate_dependence")
    if not isinstance(rel_path, str) or not rel_path.strip():
        rel_path = figure_manifest.get("dependence")
    if not isinstance(rel_path, str) or not rel_path.strip():
        return None
    return rel_path


def _safe_token(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value).strip("_") or "run"
