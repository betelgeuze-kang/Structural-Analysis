#!/usr/bin/env python3
"""Materialize the remaining source-of-truth gap classification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402
from report_release_evidence_freshness import (  # noqa: E402
    DEFAULT_ARTIFACTS,
    SOURCE_OF_TRUTH_GAP_CLASSIFICATION,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "source_of_truth_gap_classification.json"
DEFAULT_DOC = Path("docs/source-of-truth-gap-classification.md")
SCHEMA_VERSION = "source-of-truth-gap-classification.v1"
EXPECTED_CANDIDATES = {
    "accuracy_parity_scorecard",
    "product_production_ai_checkpoint_readiness",
    "goal_readiness_rollup",
    "product_goal_completion_audit",
    "goal_operator_action_board",
}


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _match_paths(value: str) -> list[Path]:
    normalized = (
        value.replace("Best current match is ", "")
        .replace("Best current matches are ", "")
        .strip()
    )
    return [
        Path(item.strip())
        for item in normalized.split(";")
        if item.strip()
    ]


def _metadata_present(payload: dict[str, Any]) -> bool:
    return all(
        key in payload
        for key in (
            "source_commit_sha",
            "engine_version",
            "input_checksums",
            "reused_evidence",
            "reuse_policy",
        )
    )


def _accuracy_scorecard_checks(payload: dict[str, Any]) -> dict[str, bool]:
    benchmark = _as_dict(payload.get("benchmark"))
    checks = _as_dict(payload.get("checks"))
    stability_suite = _as_dict(payload.get("stability_suite"))
    return {
        "overall_pass": payload.get("overall_pass") is True,
        "benchmark_contract_pass": benchmark.get("contract_pass") is True,
        "benchmark_kpi_pass": benchmark.get("kpi_pass") is True,
        "public_hf_case_count_pass": checks.get("public_hf_case_count_pass") is True,
        "direct_metric_source_pass": checks.get("direct_metric_source_pass") is True,
        "source_family_pass": checks.get("source_family_pass") is True,
        "stability_suite_pass": stability_suite.get("suite_pass") is True,
        "stability_pass": stability_suite.get("stability_pass") is True,
    }


def _row(
    source_row: dict[str, Any],
    *,
    repo_root: Path,
    freshness_labels: set[str],
) -> dict[str, Any]:
    candidate = str(source_row["candidate"])
    classification = str(source_row["classification"])
    freshness_label = str(source_row.get("freshness_label") or "")
    paths = _match_paths(str(source_row.get("current_repo_match") or ""))
    resolved_paths = [path if path.is_absolute() else repo_root / path for path in paths]
    payloads = [_load_json(path) for path in resolved_paths]
    path_presence = {
        path.as_posix(): resolved.exists()
        for path, resolved in zip(paths, resolved_paths)
    }

    live_checks: dict[str, Any] = {
        "candidate_expected": candidate in EXPECTED_CANDIDATES,
        "current_repo_match_present": all(path_presence.values()) if paths else False,
        "freshness_leaf_presence_matches": (
            freshness_label in freshness_labels
            if classification == "fix"
            else freshness_label == "" and candidate not in freshness_labels
        ),
        "metadata_present_on_current_matches": all(
            _metadata_present(payload) for payload in payloads
        )
        if payloads
        else False,
    }

    if candidate == "accuracy_parity_scorecard":
        scorecard_checks = _accuracy_scorecard_checks(payloads[0] if payloads else {})
        live_checks["accuracy_scorecard_science_checks"] = scorecard_checks
        live_checks["accuracy_scorecard_science_contract_pass"] = all(
            scorecard_checks.values()
        )
    if candidate == "product_production_ai_checkpoint_readiness":
        payload = payloads[0] if payloads else {}
        live_checks["ai_contract_status_ready"] = (
            payload.get("status") == "production_ai_ready"
            and payload.get("contracts_ready") is True
            and payload.get("production_ai_ready") is True
        )
    if classification == "aggregator-review":
        live_checks["aggregator_source_tracking_present"] = all(
            _metadata_present(payload) for payload in payloads
        )

    contract_pass = all(
        bool(value)
        for value in live_checks.values()
        if isinstance(value, bool)
    )
    return {
        **source_row,
        "status": "classified" if contract_pass else "classification_drift",
        "contract_pass": contract_pass,
        "current_repo_paths": [path.as_posix() for path in paths],
        "current_repo_path_presence": path_presence,
        "live_checks": live_checks,
    }


def build_source_of_truth_gap_classification(
    *,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    freshness_labels = {label for label, _artifact, _producer in DEFAULT_ARTIFACTS}
    rows = [
        _row(row, repo_root=repo_root, freshness_labels=freshness_labels)
        for row in SOURCE_OF_TRUTH_GAP_CLASSIFICATION
    ]
    blockers = [
        f"{row['candidate']}::classification_contract_failed"
        for row in rows
        if not row["contract_pass"]
    ]
    classifications = [str(row["classification"]) for row in rows]
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_source_of_truth_gap_classification.py"),
                Path("scripts/report_release_evidence_freshness.py"),
                DEFAULT_DOC,
                *[
                    path
                    for row in rows
                    for path in (Path(item) for item in row["current_repo_paths"])
                ],
            ],
            reused_evidence=True,
            reuse_policy=(
                "source_of_truth_gap_classification_materialized_from_freshness_policy"
            ),
            repo_root=repo_root,
        ),
        "status": "ready" if not blockers else "blocked",
        "contract_pass": not blockers,
        "reason_code": "PASS" if not blockers else "ERR_SOURCE_OF_TRUTH_GAP_CLASSIFICATION",
        "summary": {
            "candidate_count": len(rows),
            "expected_candidate_count": len(EXPECTED_CANDIDATES),
            "fix_count": classifications.count("fix"),
            "fixed_count": sum(
                1
                for row in rows
                if row["classification"] == "fix" and row["contract_pass"]
            ),
            "no_op_count": classifications.count("no-op"),
            "aggregator_review_count": classifications.count("aggregator-review"),
            "aggregator_reviewed_count": sum(
                1
                for row in rows
                if row["classification"] == "aggregator-review"
                and row["contract_pass"]
            ),
            "blocker_count": len(blockers),
        },
        "blockers": blockers,
        "rows": rows,
        "claim_boundary": (
            "This artifact classifies the five remaining source-of-truth gap "
            "candidates. It records freshness policy and live artifact checks, but "
            "does not promote aggregator rollups or replace the heavy validation "
            "receipts themselves."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_source_of_truth_gap_classification(repo_root=args.repo_root)
    out = args.out if args.out.is_absolute() else args.repo_root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json_text(payload), encoding="utf-8")
    print(
        _json_text(payload).rstrip()
        if args.json
        else (
            "source-of-truth-gap-classification: "
            f"{payload['status']} | fix={payload['summary']['fix_count']} | "
            f"aggregator_review={payload['summary']['aggregator_review_count']} | "
            f"blockers={payload['summary']['blocker_count']}"
        )
    )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
