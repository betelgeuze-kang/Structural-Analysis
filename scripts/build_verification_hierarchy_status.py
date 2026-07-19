#!/usr/bin/env python3
"""Build the non-promoting Level 1-5 structural verification hierarchy status."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.benchmark.acceptance import decide_benchmark  # noqa: E402
from structural_analysis.benchmark.analytic_frame import (  # noqa: E402
    ANALYTIC_FRAME_CATEGORIES,
    AnalyticFrameVerificationError,
    validate_analytic_frame_verification_artifact,
)
from structural_analysis.benchmark.verification_hierarchy import (  # noqa: E402
    VERIFICATION_EVIDENCE_SCHEMA_VERSION,
    build_verification_hierarchy_readiness,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_ANALYTIC_MANIFEST = (
    PRODUCTIZATION / "phase3_benchmark_factory_seed_manifest.json"
)
DEFAULT_ANALYTIC_SCORECARD = (
    PRODUCTIZATION / "phase3_benchmark_factory_seed_scorecard.json"
)
DEFAULT_ANALYTIC_FRAME_ARTIFACT = (
    PRODUCTIZATION / "analytic_frame_verification.json"
)
DEFAULT_OPERATOR_EVIDENCE = PRODUCTIZATION / "verification_hierarchy_evidence.json"
DEFAULT_OUT = PRODUCTIZATION / "verification_hierarchy_status.json"
OPERATOR_EVIDENCE_MANIFEST_SCHEMA_VERSION = (
    "structural-verification-evidence-manifest.v1"
)
_FIXED_EVALUATED_AT = "2026-07-18T00:00:00Z"
_ANALYTIC_FAMILY_POLICY = {
    "single_bar": "axial_bar",
    "patch_tests": "axial_element_patch",
}


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _resolved(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return f"sha256:{digest.hexdigest()}"


def _analytic_evidence_rows(
    *,
    repo_root: Path,
    manifest_path: Path,
    scorecard_path: Path,
) -> list[dict[str, Any]]:
    manifest = _load_json(repo_root, manifest_path)
    scorecard = _load_json(repo_root, scorecard_path)
    manifest_rows = [row for row in manifest.get("rows", []) if isinstance(row, dict)]
    scorecard_by_case = {
        str(row.get("case_id") or ""): row
        for row in scorecard.get("rows", [])
        if isinstance(row, dict) and str(row.get("case_id") or "")
    }
    manifest_sha = _sha256(_resolved(repo_root, manifest_path))
    scorecard_sha = _sha256(_resolved(repo_root, scorecard_path))
    evidence_rows: list[dict[str, Any]] = []
    for category, structural_family in _ANALYTIC_FAMILY_POLICY.items():
        selected = [
            row
            for row in manifest_rows
            if row.get("structural_family") == structural_family
            and row.get("truth_class") == "analytic_truth"
        ]
        case_ids = [str(row.get("case_id") or "") for row in selected]
        scorecard_rows = [
            scorecard_by_case[case_id]
            for case_id in case_ids
            if case_id in scorecard_by_case
        ]
        manifest_contract_pass = bool(
            selected
            and len(scorecard_rows) == len(selected)
            and all(
                str(row.get("checksum") or "").startswith("sha256:") for row in selected
            )
        )
        expected_output_contract_pass = bool(
            scorecard.get("contract_pass") is True
            and scorecard_rows
            and all(
                row.get("contract_pass") is True
                and row.get("expected_output_contract_pass") is True
                for row in scorecard_rows
            )
        )
        metric_rows = [
            {
                "metric_family": "analytic_manifest_integrity",
                "contract_pass": manifest_contract_pass,
            },
            {
                "metric_family": "analytic_expected_output_comparison",
                "contract_pass": expected_output_contract_pass,
            },
        ]
        numerical_pass = all(row["contract_pass"] for row in metric_rows)
        decision = decide_benchmark(
            metric_rows,
            decision="PASS" if numerical_pass else "FAIL",
            evaluated_at=_FIXED_EVALUATED_AT,
        )
        declared_blockers = []
        if not selected:
            declared_blockers.append(
                f"analytic_structural_family_missing:{structural_family}"
            )
        evidence_rows.append(
            {
                "schema_version": VERIFICATION_EVIDENCE_SCHEMA_VERSION,
                "evidence_id": f"repository-analytic-{category}",
                "level": 1,
                "category": category,
                "truth_basis": "analytic_closed_form",
                "declared_blockers": declared_blockers,
                "source": {
                    "url_or_doi": (
                        "generated://structural_analysis/phase3_benchmark_factory_seed"
                    ),
                    "sha256": manifest_sha,
                    "license": {
                        "id": "repo-generated-analytic-v1",
                        "approval_status": "approved",
                        "local_execution_allowed": True,
                        "commercial_use_allowed": True,
                    },
                },
                "artifacts": [
                    {
                        "path": manifest_path.as_posix(),
                        "sha256": manifest_sha,
                        "contract_pass": manifest_contract_pass,
                    },
                    {
                        "path": scorecard_path.as_posix(),
                        "sha256": scorecard_sha,
                        "contract_pass": expected_output_contract_pass,
                    },
                ],
                "decision": decision,
            }
        )
    return evidence_rows


def _analytic_frame_evidence_rows(
    *,
    repo_root: Path,
    artifact_path: Path,
) -> list[dict[str, Any]]:
    payload = _load_json(repo_root, artifact_path)
    artifact_sha = _sha256(_resolved(repo_root, artifact_path))
    validation_error = ""
    try:
        validate_analytic_frame_verification_artifact(
            payload,
            repo_root=repo_root,
            require_current_sources=True,
            rerun=True,
        )
    except (AnalyticFrameVerificationError, OSError, ValueError) as exc:
        validation_error = str(exc) or type(exc).__name__
    cases = {
        str(row.get("category") or ""): row
        for row in payload.get("cases", [])
        if isinstance(row, dict)
    }
    evidence_rows: list[dict[str, Any]] = []
    for category in ANALYTIC_FRAME_CATEGORIES:
        case = cases.get(category, {})
        comparisons = case.get("comparisons", [])
        comparison_contract_pass = bool(
            isinstance(comparisons, list)
            and comparisons
            and all(
                isinstance(row, dict) and row.get("contract_pass") is True
                for row in comparisons
            )
            and case.get("numerical_checks", {}).get("contract_pass") is True
            and case.get("contract_pass") is True
        )
        artifact_contract_pass = bool(
            not validation_error
            and payload.get("contract_pass") is True
            and artifact_sha.startswith("sha256:")
        )
        metric_rows = [
            {
                "metric_family": "analytic_frame_artifact_integrity",
                "contract_pass": artifact_contract_pass,
            },
            {
                "metric_family": "analytic_closed_form_frame_comparison",
                "contract_pass": comparison_contract_pass,
            },
        ]
        numerical_pass = all(row["contract_pass"] for row in metric_rows)
        declared_blockers: list[str] = []
        if validation_error:
            declared_blockers.append(
                f"analytic_frame_artifact_invalid:{validation_error}"
            )
        if not case:
            declared_blockers.append(f"analytic_frame_case_missing:{category}")
        evidence_rows.append(
            {
                "schema_version": VERIFICATION_EVIDENCE_SCHEMA_VERSION,
                "evidence_id": f"repository-analytic-{category}",
                "level": 1,
                "category": category,
                "truth_basis": "analytic_closed_form",
                "declared_blockers": declared_blockers,
                "source": {
                    "url_or_doi": (
                        "generated://structural_analysis/"
                        f"analytic_frame_verification/{category}"
                    ),
                    "sha256": str(case.get("model_payload_hash") or ""),
                    "license": {
                        "id": "repo-generated-analytic-v1",
                        "approval_status": "approved",
                        "local_execution_allowed": True,
                        "commercial_use_allowed": True,
                    },
                },
                "artifacts": [
                    {
                        "path": artifact_path.as_posix(),
                        "sha256": artifact_sha,
                        "contract_pass": artifact_contract_pass,
                    }
                ],
                "decision": decide_benchmark(
                    metric_rows,
                    decision="PASS" if numerical_pass else "FAIL",
                    evaluated_at=_FIXED_EVALUATED_AT,
                ),
            }
        )
    return evidence_rows


def build_verification_hierarchy_status(
    *,
    repo_root: Path = ROOT,
    analytic_manifest_path: Path = DEFAULT_ANALYTIC_MANIFEST,
    analytic_scorecard_path: Path = DEFAULT_ANALYTIC_SCORECARD,
    analytic_frame_artifact_path: Path = DEFAULT_ANALYTIC_FRAME_ARTIFACT,
    operator_evidence_path: Path = DEFAULT_OPERATOR_EVIDENCE,
) -> dict[str, Any]:
    evidence_rows = _analytic_evidence_rows(
        repo_root=repo_root,
        manifest_path=analytic_manifest_path,
        scorecard_path=analytic_scorecard_path,
    )
    evidence_rows.extend(
        _analytic_frame_evidence_rows(
            repo_root=repo_root,
            artifact_path=analytic_frame_artifact_path,
        )
    )
    input_blockers: list[str] = []
    resolved_operator = _resolved(repo_root, operator_evidence_path)
    if resolved_operator.exists():
        operator_payload = _load_json(repo_root, operator_evidence_path)
        operator_rows = operator_payload.get("evidence")
        if (
            operator_payload.get("schema_version")
            != OPERATOR_EVIDENCE_MANIFEST_SCHEMA_VERSION
        ):
            input_blockers.append(
                "verification_hierarchy_operator_manifest_schema_invalid"
            )
        if not isinstance(operator_rows, list):
            input_blockers.append(
                "verification_hierarchy_operator_manifest_evidence_invalid"
            )
        else:
            evidence_rows.extend(operator_rows)
        if not str(operator_payload.get("claim_boundary") or "").strip():
            input_blockers.append(
                "verification_hierarchy_operator_manifest_claim_boundary_missing"
            )
    return build_verification_hierarchy_readiness(
        evidence_rows,
        input_blockers=input_blockers,
    )


def write_verification_hierarchy_status(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    payload = build_verification_hierarchy_status(repo_root=repo_root)
    resolved = _resolved(repo_root, out_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def check_verification_hierarchy_status(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
) -> tuple[bool, str]:
    resolved = _resolved(repo_root, out_path)
    if not resolved.exists():
        return False, f"verification_hierarchy_status_missing:{out_path}"
    expected = build_verification_hierarchy_status(repo_root=repo_root)
    actual = _load_json(repo_root, out_path)
    if actual != expected:
        return False, "verification_hierarchy_status_mismatch"
    return True, "verification_hierarchy_status_consistent"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        ok, message = check_verification_hierarchy_status(out_path=args.out)
        print(f"Verification hierarchy status check: {message}")
        return 0 if ok else 1
    payload = write_verification_hierarchy_status(out_path=args.out)
    print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
