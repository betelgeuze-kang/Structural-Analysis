#!/usr/bin/env python3
"""Build the non-promoting five-archetype medium benchmark corpus plan."""

from __future__ import annotations

import argparse
from importlib import resources
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.benchmark.medium_corpus import (  # noqa: E402
    MEDIUM_BENCHMARK_CASE_SCHEMA_VERSION,
    MEDIUM_BENCHMARK_EVIDENCE_BINDING_PROFILE,
    REQUIRED_CASE_ARTIFACTS,
    REQUIRED_CORE_METRIC_FAMILIES,
    build_medium_benchmark_corpus_readiness,
)
from structural_analysis.benchmark.acceptance import decide_benchmark  # noqa: E402


DEFAULT_CANONICAL_REPORT = Path(
    "implementation/phase1/release/benchmark_expansion/"
    "opensees_canonical_breadth_report.json"
)
DEFAULT_LICENSE_RECEIPT = Path(
    "implementation/phase1/release_evidence/productization/"
    "phase3_opensees_medium_source_license_receipt.json"
)
DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/"
    "medium_benchmark_corpus_plan.json"
)
DEFAULT_OPERATOR_CASE_EVIDENCE = Path(
    "implementation/phase1/release_evidence/productization/"
    "medium_benchmark_case_evidence.json"
)
OPERATOR_CASE_EVIDENCE_SCHEMA_VERSION = "medium-benchmark-case-evidence-manifest.v1"
OPERATOR_CASE_EVIDENCE_SCHEMA = Path(
    "src/structural_analysis/schemas/"
    "medium_benchmark_case_evidence_manifest_v1.schema.json"
)

_CASE_POLICY = {
    "SCBF16B": {
        "archetype_id": "braced_frame_or_truss_tower",
        "size_class": "medium",
        "medium_scale_basis": "SCBF16B parser topology; 426-node family receipt; 32 GB runner envelope",
        "capabilities": ["axial_member", "bracing_or_truss", "three_dimensional"],
        "declared_blockers": [],
    },
    "SCBF16B_shell_beam_mix": {
        "archetype_id": "frame_shell_diaphragm",
        "size_class": "medium",
        "medium_scale_basis": "SCBF16B beam/shell parser topology; 426-node family receipt; 32 GB runner envelope",
        "capabilities": ["frame_3d", "shell"],
        "declared_blockers": [
            "source_url_verification_pending",
            "derived_source_provenance_pending",
        ],
    },
    "luxinzheng_megatall_model1": {
        "archetype_id": "irregular_multistory_frame",
        "size_class": "large",
        "medium_scale_basis": "606 m mega-tall model belongs to the separate large-model lane",
        "capabilities": ["frame_3d", "multi_story", "plan_or_vertical_irregularity"],
        "declared_blockers": ["large_model_substitute_not_medium"],
    },
}


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _operator_manifest_schema_pass(payload: dict[str, Any]) -> bool:
    try:
        schema = json.loads(
            resources.files("structural_analysis")
            .joinpath("schemas", OPERATOR_CASE_EVIDENCE_SCHEMA.name)
            .read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError):
        return False
    return not list(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(payload)
    )


def _artifact_plan(case_id: str) -> dict[str, dict[str, Any]]:
    base = (
        "implementation/phase1/release_evidence/productization/"
        f"medium_model_scorecard_receipts/{case_id}"
    )
    return {
        name: {
            "path": f"{base}.{name}.json",
            "sha256": "OPERATOR_ATTACHED_SHA256",
            "contract_pass": False,
        }
        for name in REQUIRED_CASE_ARTIFACTS
    }


def _source_url(
    case_id: str, row: dict[str, Any], license_receipt: dict[str, Any]
) -> str:
    for candidate in license_receipt.get("source_url_candidates", []):
        if isinstance(candidate, dict) and candidate.get("case_id") == case_id:
            return str(candidate.get("html_url") or candidate.get("raw_url") or "")
    if case_id == "SCBF16B_shell_beam_mix":
        return "https://github.com/amaelkady/OpenSEES_Models_CBF"
    if case_id == "luxinzheng_megatall_model1":
        return "http://www.luxinzheng.net/download/OpenSEES/Mega-tall_Building_Benchmark_OpenSees.htm"
    return str(row.get("source_url") or "")


def _candidate_case(
    row: dict[str, Any],
    *,
    license_receipt: dict[str, Any],
) -> dict[str, Any] | None:
    case_id = str(row.get("case_id") or "")
    policy = _CASE_POLICY.get(case_id)
    if policy is None or row.get("parser_contract_ready") is not True:
        return None
    license_evidence = (
        license_receipt.get("license_evidence")
        if isinstance(license_receipt.get("license_evidence"), dict)
        else {}
    )
    return {
        "schema_version": MEDIUM_BENCHMARK_CASE_SCHEMA_VERSION,
        "case_id": case_id,
        "archetype_id": policy["archetype_id"],
        "size_class": policy["size_class"],
        "medium_scale_basis": policy["medium_scale_basis"],
        "source_family": str(row.get("family_id") or case_id),
        "capabilities": list(policy["capabilities"]),
        "declared_blockers": list(policy["declared_blockers"]),
        "source": {
            "path": str(row.get("path") or ""),
            "url_or_doi": _source_url(case_id, row, license_receipt),
            "sha256": str(row.get("sha256") or ""),
            "license": {
                "id": "opensees-cbf-gpl-3.0-product-review",
                "spdx": str(license_evidence.get("spdx") or "GPL-3.0"),
                "approval_status": "review_required",
                "local_execution_allowed": False,
                "commercial_use_allowed": bool(
                    license_receipt.get("commercial_use_allowed") is True
                ),
            },
        },
        "reference_solver": {
            "name": "OpenSees",
            "version": "OPERATOR_VERIFICATION_REQUIRED",
            "version_verified": False,
            "solver_class": "open_source",
            "independent_from_product": True,
        },
        "artifacts": _artifact_plan(case_id),
        "metric_families": list(REQUIRED_CORE_METRIC_FAMILIES),
        "decision": decide_benchmark(
            [
                {"metric_family": family, "contract_pass": False}
                for family in REQUIRED_CORE_METRIC_FAMILIES
            ],
            decision="FAIL",
            evaluated_at="2026-07-18T00:00:00Z",
        ),
    }


def build_medium_benchmark_corpus_plan(
    *,
    repo_root: Path = ROOT,
    canonical_report_path: Path = DEFAULT_CANONICAL_REPORT,
    license_receipt_path: Path = DEFAULT_LICENSE_RECEIPT,
    operator_case_evidence_path: Path = DEFAULT_OPERATOR_CASE_EVIDENCE,
) -> dict[str, Any]:
    resolved_operator_evidence = (
        operator_case_evidence_path
        if operator_case_evidence_path.is_absolute()
        else repo_root / operator_case_evidence_path
    )
    if resolved_operator_evidence.exists():
        operator_payload = _load_json(repo_root, operator_case_evidence_path)
        operator_cases = operator_payload.get("cases")
        input_blockers: list[str] = []
        if not _operator_manifest_schema_pass(operator_payload):
            input_blockers.append("medium_corpus_operator_manifest_schema_invalid")
        if not isinstance(operator_cases, list):
            input_blockers.append("medium_corpus_operator_manifest_cases_invalid")
        if not str(operator_payload.get("claim_boundary") or "").strip():
            input_blockers.append(
                "medium_corpus_operator_manifest_claim_boundary_missing"
            )
        if (
            operator_payload.get("binding_profile")
            != MEDIUM_BENCHMARK_EVIDENCE_BINDING_PROFILE
        ):
            input_blockers.append(
                "medium_corpus_operator_manifest_binding_profile_invalid"
            )
        return build_medium_benchmark_corpus_readiness(
            operator_cases if isinstance(operator_cases, list) else [],
            repo_root=repo_root,
            input_blockers=input_blockers,
        )
    canonical_report = _load_json(repo_root, canonical_report_path)
    license_receipt = _load_json(repo_root, license_receipt_path)
    cases = [
        case
        for row in canonical_report.get("rows", [])
        if isinstance(row, dict)
        for case in [_candidate_case(row, license_receipt=license_receipt)]
        if case is not None
    ]
    return build_medium_benchmark_corpus_readiness(cases, repo_root=repo_root)


def write_medium_benchmark_corpus_plan(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    payload = build_medium_benchmark_corpus_plan(repo_root=repo_root)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def check_medium_benchmark_corpus_plan(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
) -> tuple[bool, str]:
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"medium_benchmark_corpus_plan_missing:{out_path}"
    expected = build_medium_benchmark_corpus_plan(repo_root=repo_root)
    actual = _load_json(repo_root, out_path)
    if actual != expected:
        return False, "medium_benchmark_corpus_plan_mismatch"
    return True, "medium_benchmark_corpus_plan_consistent"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        ok, message = check_medium_benchmark_corpus_plan(out_path=args.out)
        print(f"Medium benchmark corpus plan check: {message}")
        return 0 if ok else 1
    payload = write_medium_benchmark_corpus_plan(out_path=args.out)
    print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
