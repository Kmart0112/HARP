#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ALLOWED_SCENARIOS = {
    "aggregate_only",
    "source_only",
    "all_features",
    "variant_compare",
    "baseline",
}

REQUIRED_COLUMNS = [
    "scenario",
    "group_id",
    "tested_set",
    "auc",
    "logloss",
    "brier",
    "delta_auc",
    "delta_logloss",
    "delta_brier",
]

SIMPLE_ORDER = {
    "aggregate_only": 0,
    "source_only": 1,
    "all_features": 2,
}

DECISION_COLUMNS = [
    "group_id",
    "decision_type",
    "winner_set",
    "loser_sets",
    "reason",
    "delta_auc",
    "delta_logloss",
    "delta_brier",
]


@dataclass(frozen=True)
class CandidateResult:
    scenario: str
    group_id: str
    tested_set: str
    auc: float
    logloss: float
    brier: float
    delta_auc: float
    delta_logloss: float
    delta_brier: float

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> "CandidateResult":
        return cls(
            scenario=row["scenario"].strip(),
            group_id=row["group_id"].strip(),
            tested_set=row["tested_set"].strip(),
            auc=float(row["auc"]),
            logloss=float(row["logloss"]),
            brier=float(row["brier"]),
            delta_auc=float(row["delta_auc"]),
            delta_logloss=float(row["delta_logloss"]),
            delta_brier=float(row["delta_brier"]),
        )

    def score_tuple(self) -> tuple[float, float, float]:
        return (self.delta_auc, -self.delta_logloss, -self.delta_brier)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Judge feature keep/drop winners from ablation CSV.")
    parser.add_argument("--results-csv", required=True, type=Path)
    parser.add_argument("--variant-map", required=True, type=Path)
    parser.add_argument("--output-report", required=True, type=Path)
    parser.add_argument("--output-decisions", required=True, type=Path)
    parser.add_argument("--auc-threshold", type=float, default=1e-5)
    parser.add_argument("--logloss-threshold", type=float, default=-1e-5)
    return parser.parse_args()


def parse_scalar(text: str) -> str:
    text = text.strip()
    if text.startswith(("'", '"')) and text.endswith(("'", '"')) and len(text) >= 2:
        return text[1:-1]
    return text


def parse_inline_list(text: str) -> list[str]:
    text = text.strip()
    if not (text.startswith("[") and text.endswith("]")):
        return []
    inner = text[1:-1].strip()
    if not inner:
        return []
    items = [parse_scalar(x.strip()) for x in inner.split(",")]
    return [x for x in items if x]


def parse_variant_map(path: Path) -> tuple[str, list[dict[str, Any]]]:
    if not path.exists():
        raise ValueError(f"variant-map not found: {path}")

    run_name: str | None = None
    groups: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_candidates = False

    lines = path.read_text(encoding="utf-8").splitlines()
    for raw in lines:
        line = raw.split("#", 1)[0].rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("run_name:"):
            run_name = parse_scalar(stripped.split(":", 1)[1].strip())
            in_candidates = False
            continue

        if stripped == "variant_groups:":
            in_candidates = False
            continue

        if stripped.startswith("- group_id:"):
            if current is not None:
                groups.append(current)
            group_id = parse_scalar(stripped.split(":", 1)[1].strip())
            current = {
                "group_id": group_id,
                "candidates": [],
                "selection_mode": "tournament_one_winner",
            }
            in_candidates = False
            continue

        if current is None:
            continue

        if stripped.startswith("group_id:"):
            current["group_id"] = parse_scalar(stripped.split(":", 1)[1].strip())
            in_candidates = False
            continue

        if stripped.startswith("candidates:"):
            after = stripped.split(":", 1)[1].strip()
            if after:
                current["candidates"] = parse_inline_list(after)
                in_candidates = False
            else:
                in_candidates = True
            continue

        if in_candidates and stripped.startswith("- "):
            current["candidates"].append(parse_scalar(stripped[2:].strip()))
            continue

        if stripped.startswith("selection_mode:"):
            current["selection_mode"] = parse_scalar(stripped.split(":", 1)[1].strip())
            in_candidates = False
            continue

    if current is not None:
        groups.append(current)

    if not run_name:
        raise ValueError("variant-map requires non-empty run_name")
    if not groups:
        raise ValueError("variant-map requires non-empty variant_groups list")

    seen = set()
    normalized = []
    for group in groups:
        group_id = str(group.get("group_id", "")).strip()
        if not group_id:
            raise ValueError("each variant group requires non-empty group_id")
        if group_id in seen:
            raise ValueError(f"duplicate variant group_id: {group_id}")
        seen.add(group_id)

        candidates = group.get("candidates", [])
        if (
            not isinstance(candidates, list)
            or len(candidates) < 2
            or not all(isinstance(c, str) and c.strip() for c in candidates)
        ):
            raise ValueError(f"group '{group_id}' requires 2+ non-empty string candidates")

        selection_mode = str(group.get("selection_mode", "tournament_one_winner")).strip()
        if selection_mode != "tournament_one_winner":
            raise ValueError(
                f"group '{group_id}' has invalid selection_mode '{selection_mode}', "
                "expected 'tournament_one_winner'"
            )

        normalized.append(
            {
                "group_id": group_id,
                "candidates": [c.strip() for c in candidates],
                "selection_mode": selection_mode,
            }
        )

    return run_name, normalized


def read_results_csv(path: Path) -> list[CandidateResult]:
    if not path.exists():
        raise ValueError(f"Results CSV not found: {path}")

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("results-csv has no header")

        missing = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
        if missing:
            raise ValueError(f"results-csv is missing required columns: {missing}")

        rows: list[CandidateResult] = []
        for raw in reader:
            scenario = (raw.get("scenario") or "").strip()
            group_id = (raw.get("group_id") or "").strip()
            tested_set = (raw.get("tested_set") or "").strip()
            if scenario not in ALLOWED_SCENARIOS:
                raise ValueError(f"results-csv has invalid scenario value: {scenario}")
            if not group_id:
                raise ValueError("results-csv contains empty group_id")
            if not tested_set:
                raise ValueError("results-csv contains empty tested_set")

            row = CandidateResult.from_dict(raw)
            rows.append(row)

    if not rows:
        raise ValueError("results-csv has no data rows")
    return rows


def is_improved(row: CandidateResult, auc_threshold: float, logloss_threshold: float) -> bool:
    return row.delta_auc > auc_threshold and row.delta_logloss < logloss_threshold


def is_near_tie(
    a: CandidateResult,
    b: CandidateResult,
    auc_threshold: float,
    logloss_threshold: float,
) -> bool:
    logloss_eps = abs(logloss_threshold)
    return abs(a.delta_auc - b.delta_auc) <= auc_threshold and abs(a.delta_logloss - b.delta_logloss) <= logloss_eps


def best_by_metrics(rows: list[CandidateResult]) -> CandidateResult:
    return sorted(rows, key=lambda r: r.score_tuple(), reverse=True)[0]


def join_losers(values: list[str]) -> str:
    return "|".join(values) if values else ""


def decide_aggregate_groups(
    rows: list[CandidateResult],
    auc_threshold: float,
    logloss_threshold: float,
) -> tuple[list[dict[str, Any]], list[str]]:
    decisions: list[dict[str, Any]] = []
    unresolved_groups: list[str] = []

    by_group: dict[str, dict[str, list[CandidateResult]]] = {}
    for row in rows:
        if row.scenario not in {"aggregate_only", "source_only", "all_features"}:
            continue
        by_group.setdefault(row.group_id, {}).setdefault(row.scenario, []).append(row)

    for group_id in sorted(by_group.keys()):
        scenarios = by_group[group_id]
        missing = [s for s in ["aggregate_only", "source_only", "all_features"] if s not in scenarios]
        if missing:
            decisions.append(
                {
                    "group_id": group_id,
                    "decision_type": "aggregate_3way",
                    "winner_set": "unresolved",
                    "loser_sets": "",
                    "reason": f"missing_scenarios:{','.join(missing)}",
                    "delta_auc": float("nan"),
                    "delta_logloss": float("nan"),
                    "delta_brier": float("nan"),
                }
            )
            unresolved_groups.append(group_id)
            continue

        scenario_winners = [best_by_metrics(scenarios[s]) for s in ["aggregate_only", "source_only", "all_features"]]
        improved = [r for r in scenario_winners if is_improved(r, auc_threshold, logloss_threshold)]
        pool = improved if improved else scenario_winners
        provisional = best_by_metrics(pool)
        tied = [r for r in pool if is_near_tie(r, provisional, auc_threshold, logloss_threshold)]

        tie_applied = False
        if len(tied) > 1:
            final = sorted(tied, key=lambda r: SIMPLE_ORDER.get(r.scenario, 99))[0]
            tie_applied = True
        else:
            final = provisional

        losers = [best_by_metrics(scenarios[s]).tested_set for s in ["aggregate_only", "source_only", "all_features"] if s != final.scenario]
        reason = "improved_winner" if improved else "no_global_improvement_relative_best"
        if tie_applied:
            reason += "_with_simple_preference"

        decisions.append(
            {
                "group_id": group_id,
                "decision_type": "aggregate_3way",
                "winner_set": final.tested_set,
                "loser_sets": join_losers(losers),
                "reason": reason,
                "delta_auc": final.delta_auc,
                "delta_logloss": final.delta_logloss,
                "delta_brier": final.delta_brier,
            }
        )

    return decisions, unresolved_groups


def decide_variant_groups(
    rows: list[CandidateResult],
    variant_groups: list[dict[str, Any]],
    auc_threshold: float,
    logloss_threshold: float,
) -> tuple[list[dict[str, Any]], list[str]]:
    decisions: list[dict[str, Any]] = []
    unresolved_groups: list[str] = []

    by_group: dict[str, list[CandidateResult]] = {}
    for row in rows:
        if row.scenario == "variant_compare":
            by_group.setdefault(row.group_id, []).append(row)

    for group in variant_groups:
        group_id = group["group_id"]
        candidates = group["candidates"]
        sub = [r for r in by_group.get(group_id, []) if r.tested_set in candidates]
        found = sorted({r.tested_set for r in sub})
        missing = [c for c in candidates if c not in found]

        if missing:
            decisions.append(
                {
                    "group_id": group_id,
                    "decision_type": "variant_compare",
                    "winner_set": "unresolved",
                    "loser_sets": "",
                    "reason": f"missing_candidates:{','.join(missing)}",
                    "delta_auc": float("nan"),
                    "delta_logloss": float("nan"),
                    "delta_brier": float("nan"),
                }
            )
            unresolved_groups.append(group_id)
            continue

        improved = [r for r in sub if is_improved(r, auc_threshold, logloss_threshold)]
        if not improved:
            decisions.append(
                {
                    "group_id": group_id,
                    "decision_type": "variant_compare",
                    "winner_set": "current_keep",
                    "loser_sets": "",
                    "reason": "no_candidate_improved",
                    "delta_auc": 0.0,
                    "delta_logloss": 0.0,
                    "delta_brier": 0.0,
                }
            )
            continue

        winner = best_by_metrics(improved)
        losers = [r.tested_set for r in sub if r.tested_set != winner.tested_set]
        decisions.append(
            {
                "group_id": group_id,
                "decision_type": "variant_compare",
                "winner_set": winner.tested_set,
                "loser_sets": join_losers(losers),
                "reason": "best_improved_candidate",
                "delta_auc": winner.delta_auc,
                "delta_logloss": winner.delta_logloss,
                "delta_brier": winner.delta_brier,
            }
        )

    return decisions, unresolved_groups


def markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_該当なし_\n"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = []
    for row in rows:
        values = []
        for col in columns:
            value = row.get(col, "")
            if isinstance(value, float):
                value = "" if math.isnan(value) else f"{value:.9f}"
            values.append(str(value))
        body.append("| " + " | ".join(values) + " |")
    return "\n".join([header, sep] + body) + "\n"


def build_report(
    run_name: str,
    results_csv: Path,
    variant_map: Path,
    decisions: list[dict[str, Any]],
    unresolved_groups: list[str],
    auc_threshold: float,
    logloss_threshold: float,
) -> str:
    aggregate_rows = [d for d in decisions if d["decision_type"] == "aggregate_3way"]
    variant_rows = [d for d in decisions if d["decision_type"] == "variant_compare"]
    unresolved_rows = [d for d in decisions if d["winner_set"] == "unresolved"]

    lines = [
        f"# 特徴量取捨選択レポート（{run_name}）",
        "",
        "## 1. 実行概要",
        f"- results_csv: `{results_csv}`",
        f"- variant_map: `{variant_map}`",
        f"- 判定閾値: delta_auc > {auc_threshold}, delta_logloss < {logloss_threshold}",
        "",
        "## 2. 集約3条件の判定結果",
        markdown_table(
            aggregate_rows,
            [
                "group_id",
                "winner_set",
                "loser_sets",
                "reason",
                "delta_auc",
                "delta_logloss",
                "delta_brier",
            ],
        ),
        "",
        "## 3. 算出法variantの判定結果",
        markdown_table(
            variant_rows,
            [
                "group_id",
                "winner_set",
                "loser_sets",
                "reason",
                "delta_auc",
                "delta_logloss",
                "delta_brier",
            ],
        ),
        "",
        "## 4. unresolved グループ",
    ]

    if unresolved_rows:
        lines.append(markdown_table(unresolved_rows, ["group_id", "decision_type", "reason"]))
    else:
        lines.append("- なし")

    lines.extend(
        [
            "",
            "## 5. 反映ルール",
            "- winner は `pipeline/config/feature_registry.yml` の対象 set で `status: on` を維持する。",
            "- loser は `pipeline/config/feature_registry.yml` の対象 set で `status: off` に更新する。",
            "- unresolved は強制dropせず、次回検証対象に回す。",
            "",
            "## 6. 実行メモ",
            f"- decision_rows: {len(decisions)}",
            f"- unresolved_count: {len(unresolved_groups)}",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def write_decision_csv(path: Path, decisions: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DECISION_COLUMNS)
        writer.writeheader()
        for row in decisions:
            normalized = {k: row.get(k, "") for k in DECISION_COLUMNS}
            for key in ["delta_auc", "delta_logloss", "delta_brier"]:
                val = normalized[key]
                if isinstance(val, float) and math.isnan(val):
                    normalized[key] = ""
            writer.writerow(normalized)


def main() -> None:
    args = parse_args()
    if args.logloss_threshold >= 0:
        raise ValueError("--logloss-threshold must be negative, e.g. -1e-5")

    rows = read_results_csv(args.results_csv)
    run_name, variant_groups = parse_variant_map(args.variant_map)

    aggregate_decisions, aggregate_unresolved = decide_aggregate_groups(
        rows=rows,
        auc_threshold=args.auc_threshold,
        logloss_threshold=args.logloss_threshold,
    )
    variant_decisions, variant_unresolved = decide_variant_groups(
        rows=rows,
        variant_groups=variant_groups,
        auc_threshold=args.auc_threshold,
        logloss_threshold=args.logloss_threshold,
    )
    decisions = aggregate_decisions + variant_decisions
    unresolved = sorted(set(aggregate_unresolved + variant_unresolved))

    report = build_report(
        run_name=run_name,
        results_csv=args.results_csv,
        variant_map=args.variant_map,
        decisions=decisions,
        unresolved_groups=unresolved,
        auc_threshold=args.auc_threshold,
        logloss_threshold=args.logloss_threshold,
    )

    write_decision_csv(args.output_decisions, decisions)
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(report, encoding="utf-8")

    print(f"[OK] decisions: {args.output_decisions}")
    print(f"[OK] report: {args.output_report}")


if __name__ == "__main__":
    main()
