from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generic, TypeVar

from harp.interface.ports import FileGatewayPort, TrackingPort, TrackingRunRecord


_ResultT = TypeVar("_ResultT")


@dataclass(frozen=True)
class ThemeRunState(Generic[_ResultT]):
    parent_run_id: str
    theme_status: str
    theme_revision: int
    append_history: tuple[str, ...]
    child_run_ids_by_scenario: dict[str, tuple[str, ...]]
    effective_results: tuple[_ResultT, ...]
    path_overrides: dict[str, str]


def load_theme_state(
    *,
    tracking: TrackingPort,
    parent_run_id: str,
    expected_theme_kind: str,
    expected_identity_tags: dict[str, str],
    fallback_paths: dict[str, str],
    result_loader: Callable[[dict[str, object], str], _ResultT],
    scenario_name_resolver: Callable[[dict[str, object], TrackingRunRecord], str],
    summary_path: str = "summary.json",
) -> ThemeRunState[_ResultT]:
    parent_run = tracking.get_run(parent_run_id)
    theme_status = parent_run.tags.get("theme_status", "").strip()
    if theme_status != "open":
        raise ValueError(f"parent run is not appendable: run_id={parent_run_id} theme_status={theme_status or 'missing'}")
    if parent_run.tags.get("theme_kind") not in {"", expected_theme_kind}:
        raise ValueError(f"parent run is not a {expected_theme_kind} theme: {parent_run_id}")
    for key, expected in expected_identity_tags.items():
        actual = parent_run.tags.get(key, "").strip()
        if actual != expected:
            raise ValueError(
                f"parent run identity mismatch: run_id={parent_run_id} key={key} expected={expected!r} actual={actual!r}"
            )

    parent_summary = tracking.read_dict_artifact(parent_run_id, summary_path)
    path_overrides = {
        key: str(parent_summary.get(key) or parent_run.tags.get(key) or fallback)
        for key, fallback in fallback_paths.items()
    }
    append_history = tuple(str(item) for item in parent_summary.get("append_history", []) if str(item).strip())
    theme_revision = int(parent_summary.get("theme_revision", parent_run.tags.get("theme_revision", "1")))
    effective_results = tuple(
        collect_latest_child_summaries(
            tracking=tracking,
            parent_run_id=parent_run_id,
            result_loader=result_loader,
            scenario_name_resolver=scenario_name_resolver,
            summary_path=summary_path,
        ).values()
    )
    child_run_ids_by_scenario: dict[str, list[str]] = {}
    for child_run in tracking.list_child_runs(parent_run_id):
        scenario_name = child_run.tags.get("scenario_name", child_run.run_name)
        child_run_ids_by_scenario.setdefault(scenario_name, []).append(child_run.run_id)
    return ThemeRunState(
        parent_run_id=parent_run_id,
        theme_status=theme_status,
        theme_revision=theme_revision,
        append_history=append_history,
        child_run_ids_by_scenario={key: tuple(value) for key, value in child_run_ids_by_scenario.items()},
        effective_results=effective_results,
        path_overrides=path_overrides,
    )


def build_attempt_counts(theme_state: ThemeRunState[object] | None) -> dict[str, int]:
    if theme_state is None:
        return {}
    return {scenario_name: len(run_ids) for scenario_name, run_ids in theme_state.child_run_ids_by_scenario.items()}


def collect_latest_child_summaries(
    *,
    tracking: TrackingPort,
    parent_run_id: str,
    result_loader: Callable[[dict[str, object], str], _ResultT],
    scenario_name_resolver: Callable[[dict[str, object], TrackingRunRecord], str],
    summary_path: str = "summary.json",
) -> dict[str, _ResultT]:
    latest_by_scenario: dict[str, tuple[int, int, _ResultT]] = {}
    for child_run in tracking.list_child_runs(parent_run_id):
        if child_run.status == "FAILED":
            continue
        summary = tracking.read_dict_artifact(child_run.run_id, summary_path)
        scenario_name = scenario_name_resolver(summary, child_run)
        attempt_number = int(summary.get("scenario_attempt", child_run.tags.get("scenario_attempt", "1")))
        result = result_loader(summary, child_run.run_id)
        sort_key = (attempt_number, child_run.start_time or 0)
        previous = latest_by_scenario.get(scenario_name)
        if previous is None or sort_key >= (previous[0], previous[1]):
            latest_by_scenario[scenario_name] = (attempt_number, child_run.start_time or 0, result)
    return {name: payload[2] for name, payload in latest_by_scenario.items()}


def sync_attempt_statuses(
    *,
    tracking: TrackingPort,
    parent_run_id: str,
    scenario_names: set[str],
    effective_run_ids: set[str],
) -> None:
    for child_run in tracking.list_child_runs(parent_run_id):
        scenario_name = child_run.tags.get("scenario_name", child_run.run_name)
        if scenario_name not in scenario_names:
            continue
        if child_run.status == "FAILED":
            tracking.log_tags(child_run.run_id, {"attempt_status": "failed"})
            continue
        tracking.log_tags(
            child_run.run_id,
            {"attempt_status": "successful" if child_run.run_id in effective_run_ids else "superseded"},
        )


def publish_parent_artifacts(
    *,
    file_gateway: FileGatewayPort,
    tracking: TrackingPort,
    parent_run_id: str,
    run_log_dir: str,
    theme_revision: int,
    latest_artifacts: dict[str, str],
    revision_artifacts: dict[str, str],
    summary: dict[str, object],
) -> None:
    latest_dir = Path(run_log_dir) / "parent_artifacts" / "latest"
    revision_dir = Path(run_log_dir) / "parent_artifacts" / "revisions" / str(theme_revision)

    for name, src in latest_artifacts.items():
        dst = str(latest_dir / name)
        file_gateway.copy(src, dst)
        tracking.log_artifact(parent_run_id, dst, artifact_path="reports")

    for name, src in revision_artifacts.items():
        dst = str(revision_dir / name)
        file_gateway.copy(src, dst)
        tracking.log_artifact(parent_run_id, dst, artifact_path=f"revisions/{theme_revision}")

    tracking.log_dict(parent_run_id, summary, artifact_file="summary.json")
    tracking.log_dict(parent_run_id, summary, artifact_file=f"revisions/{theme_revision}/summary.json")


def safe_token(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value).strip("_") or "run"


def terminate_safely(tracking: TrackingPort, run_id: str | None, status: str) -> None:
    if run_id is None:
        return
    try:
        tracking.set_terminated(run_id, status=status)
    except Exception:
        pass
