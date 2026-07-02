#!/usr/bin/env python3
"""Track fresh full-validation lanes separately from release evidence freshness."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402

REPO_ROOT = SCRIPT_DIR.parent
PHASE1_DIR = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

from validate_fresh_validation_receipt import validate_payload as validate_receipt_payload  # noqa: E402

DEFAULT_RECEIPT_SCHEMA = PHASE1_DIR / "fresh_validation_receipt.schema.json"


SCHEMA_VERSION = "fresh-full-validation-lane-status.v1"
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/fresh_full_validation_lane_status.json")
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_DOCS = (
    Path("docs/release-publication-runbook.md"),
    Path("docs/commercialization-gap-current-state.md"),
)
DEFAULT_RECEIPT_ROOT = Path("implementation/phase1/release_evidence/full_validation")

FRESH_VALIDATION_PATH_ALIASES: dict[str, tuple[Path, ...]] = {
    "implementation/phase1/contact_readiness_report.json": (
        Path("implementation/phase1/release_evidence/performance/contact_readiness_report.json"),
    ),
    "implementation/phase1/foundation_soil_link_gate_report.json": (
        Path("implementation/phase1/release_evidence/performance/foundation_soil_link_gate_report.json"),
    ),
    "implementation/phase1/gpu_bottleneck_audit_report.json": (
        Path("implementation/phase1/release_evidence/performance/gpu_bottleneck_audit_report.json"),
    ),
    "implementation/phase1/ssi_boundary_gate_report.json": (
        Path("implementation/phase1/release_evidence/performance/ssi_boundary_gate_report.json"),
    ),
    "implementation/phase1/structural_contact_gate_report.json": (
        Path("implementation/phase1/release_evidence/surface/structural_contact_gate_report.json"),
    ),
    "implementation/phase1/release/midas_native_roundtrip/midas_native_writeback_diff_receipts_report.json": (
        Path("implementation/phase1/release_evidence/midas/midas_native_writeback_diff_receipts_report.json"),
    ),
    "implementation/phase1/release/design_optimization/design_optimization_solver_loop_long_report.json": (
        Path("implementation/phase1/release_evidence/kds/design_optimization_solver_loop_long_report.json"),
    ),
}

DEFAULT_LANES: tuple[dict[str, Any], ...] = (
    {
        "lane_id": "commercial_benchmark_torch",
        "runner": "torch_capable_benchmark_validation",
        "materialized_paths": [Path("implementation/phase1/release_evidence/commercial/commercial_readiness_report.json")],
        "doc_terms": ["torch-capable benchmark validation lane"],
    },
    {
        "lane_id": "gpu_hip_solver",
        "runner": "gpu_capable_rocm_hip_validation",
        "materialized_paths": [Path("implementation/phase1/release_evidence/gpu/solver_hip_e2e_contract_report.json")],
        "doc_terms": ["GPU-capable validation task"],
    },
    {
        "lane_id": "performance_profile",
        "runner": "performance_validation",
        "materialized_paths": [Path("implementation/phase1/release_evidence/performance")],
        "doc_terms": ["performance evidence"],
    },
    {
        "lane_id": "surface_material_contact",
        "runner": "heavy_surface_material_contact_validation",
        "materialized_paths": [Path("implementation/phase1/release_evidence/surface")],
        "doc_terms": ["full surface/contact/material refresh", "heavy validation lane"],
    },
    {
        "lane_id": "midas_exact_refresh",
        "runner": "midas_validation",
        "materialized_paths": [Path("implementation/phase1/release_evidence/midas")],
        "doc_terms": ["MIDAS validation lane"],
    },
    {
        "lane_id": "productization_heavy_profile",
        "runner": "heavy_productization_validation",
        "materialized_paths": [
            Path("implementation/phase1/release_evidence/productization/ndtha_residual_gate_report.json")
        ],
        "doc_terms": ["NDTHA long-profile", "heavy validation lane"],
    },
    {
        "lane_id": "external_benchmark_refresh",
        "runner": "benchmark_productization_validation",
        "materialized_paths": [
            Path("implementation/phase1/release_evidence/productization/hardest_external_10case_kickoff_gate_report.json")
        ],
        "doc_terms": ["external kickoff refresh", "benchmark/productization validation lane"],
    },
    {
        "lane_id": "design_optimization_refresh",
        "runner": "design_optimization_validation",
        "materialized_paths": [
            Path("implementation/phase1/release_evidence/productization/design_optimization_cost_reduction_smoke_report.json")
        ],
        "doc_terms": ["solver-loop smoke refresh", "design optimization validation lane"],
    },
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_docs(paths: tuple[Path, ...]) -> str:
    chunks = []
    for path in paths:
        if path.exists():
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks).lower()


def _truthy_contract(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass") is True
        or str(payload.get("reason_code", "")).strip().upper() == "PASS"
        or str(payload.get("status", "")).strip().lower() in {"pass", "ready", "closed"}
    )


def _has_metadata(payload: dict[str, Any]) -> bool:
    return all(
        key in payload and payload.get(key) not in (None, "", {})
        for key in ("generated_at", "source_commit_sha", "engine_version", "input_checksums")
    ) and "reused_evidence" in payload


def _load_receipt_schema() -> dict[str, Any]:
    return _load_json(DEFAULT_RECEIPT_SCHEMA)


def _validate_receipt(receipt_path: Path, schema: dict[str, Any]) -> dict[str, Any]:
    payload = _load_json(receipt_path)
    if not payload:
        return {
            "contract_pass": False,
            "reason_code": "ERR_FRESH_VALIDATION_RECEIPT_INVALID",
            "blockers": ["fresh_validation_receipt_invalid:payload_unreadable"],
        }
    if not schema:
        return {
            "contract_pass": False,
            "reason_code": "ERR_FRESH_VALIDATION_RECEIPT_INVALID",
            "blockers": ["fresh_validation_receipt_invalid:schema_unreadable"],
        }
    return validate_receipt_payload(payload, schema)


def _repo_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def _resolve_artifact_path_with_alias(path_value: str, receipt_path: Path) -> tuple[Path, dict[str, Any] | None]:
    path = Path(path_value)
    if path.is_absolute() or path.exists():
        return path, None
    receipt_relative = receipt_path.parent / path
    if receipt_relative.exists():
        return receipt_relative, None
    for alias in FRESH_VALIDATION_PATH_ALIASES.get(path_value, ()):
        alias_path = _repo_path(alias)
        if alias_path.exists():
            return alias_path, {
                "original_path": path_value,
                "resolved_path": str(alias),
                "resolution": "legacy_release_evidence_path_alias",
                "claim_boundary": (
                    "Alias resolves a tracked path migration only. Artifact integrity still "
                    "requires the resolved file sha256 to match the receipt expectation."
                ),
            }
    return path, None


def _resolve_artifact_path(path_value: str, receipt_path: Path) -> Path:
    resolved, _alias = _resolve_artifact_path_with_alias(path_value, receipt_path)
    return resolved


def _sha256_ref(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _receipt_artifact_integrity_check(
    receipt_payload: dict[str, Any],
    *,
    receipt_path: Path,
) -> dict[str, Any]:
    blockers: list[str] = []
    path_aliases: list[dict[str, Any]] = []
    receipt_artifacts = receipt_payload.get("receipt_artifacts")
    if isinstance(receipt_artifacts, list):
        for index, artifact in enumerate(receipt_artifacts):
            if not isinstance(artifact, dict):
                continue
            path_value = artifact.get("path")
            expected_sha = artifact.get("sha256")
            if not isinstance(path_value, str) or not isinstance(expected_sha, str):
                continue
            resolved, alias_metadata = _resolve_artifact_path_with_alias(path_value, receipt_path)
            actual_sha = _sha256_ref(resolved)
            if alias_metadata is not None:
                path_aliases.append(
                    {
                        **alias_metadata,
                        "receipt_field": f"receipt_artifacts[{index}].path",
                        "expected_sha256": expected_sha,
                        "actual_sha256": actual_sha,
                        "sha256_match": actual_sha is not None and actual_sha.lower() == expected_sha.lower(),
                    }
                )
            if actual_sha is None:
                blockers.append(f"receipt_artifacts[{index}].path_missing:{path_value}")
            elif actual_sha.lower() != expected_sha.lower():
                blockers.append(f"receipt_artifacts[{index}].sha256_mismatch:{path_value}")

    input_checksums = receipt_payload.get("input_checksums")
    if isinstance(input_checksums, dict):
        for path_value, expected_sha in input_checksums.items():
            if not isinstance(path_value, str) or not isinstance(expected_sha, str):
                continue
            resolved, alias_metadata = _resolve_artifact_path_with_alias(path_value, receipt_path)
            actual_sha = _sha256_ref(resolved)
            if alias_metadata is not None:
                path_aliases.append(
                    {
                        **alias_metadata,
                        "receipt_field": "input_checksums",
                        "expected_sha256": expected_sha,
                        "actual_sha256": actual_sha,
                        "sha256_match": actual_sha is not None and actual_sha.lower() == expected_sha.lower(),
                    }
                )
            if actual_sha is None:
                blockers.append(f"input_checksums.path_missing:{path_value}")
            elif actual_sha.lower() != expected_sha.lower():
                blockers.append(f"input_checksums.sha256_mismatch:{path_value}")
    return {
        "blockers": blockers,
        "path_aliases": path_aliases,
    }


def _receipt_artifact_integrity_blockers(
    receipt_payload: dict[str, Any],
    *,
    receipt_path: Path,
) -> list[str]:
    return list(_receipt_artifact_integrity_check(receipt_payload, receipt_path=receipt_path)["blockers"])


def _fresh_validation_blocker_grouping_metadata(blockers: list[str]) -> dict[str, Any]:
    group_specs = [
        (
            "lane_publication_boundary",
            {
                "scope": "release_publication_boundary",
                "description": "Materialized evidence and documentation boundary gaps.",
                "matches": (
                    "materialized_publication_evidence_missing",
                    "validation_lane_boundary_missing_from_docs",
                ),
            },
        ),
        (
            "fresh_receipt_presence",
            {
                "scope": "fresh_validation_receipt_required",
                "description": "Missing fresh validation receipts for named lanes.",
                "matches": ("fresh_validation_receipt_missing",),
            },
        ),
        (
            "fresh_receipt_metadata_freshness",
            {
                "scope": "fresh_validation_receipt_required",
                "description": "Receipt metadata and reused-evidence freshness failures.",
                "matches": (
                    "fresh_validation_receipt_metadata_missing",
                    "fresh_validation_receipt_reuses_evidence",
                ),
            },
        ),
        (
            "fresh_receipt_identity",
            {
                "scope": "fresh_validation_receipt_required",
                "description": "Receipt pass, lane identity, or runner identity failures.",
                "matches": (
                    "fresh_validation_receipt_not_green",
                    "fresh_validation_receipt_lane_mismatch",
                    "fresh_validation_receipt_runner_mismatch",
                ),
            },
        ),
        (
            "fresh_receipt_schema_contract",
            {
                "scope": "fresh_validation_receipt_required",
                "description": "Fresh validation receipt schema or validator failures.",
                "matches": (
                    "fresh_validation_receipt_invalid",
                    "fresh_validation_receipt_invalid:",
                ),
            },
        ),
        (
            "fresh_receipt_artifact_integrity",
            {
                "scope": "fresh_validation_receipt_required",
                "description": "Receipt artifact checksum or path integrity failures.",
                "matches": (
                    "fresh_validation_receipt_artifact_integrity_failed",
                    "fresh_validation_receipt_artifact_integrity_failed:",
                ),
            },
        ),
    ]
    groups: dict[str, dict[str, Any]] = {}
    classified: set[str] = set()
    for group_name, spec in group_specs:
        matches = tuple(str(match) for match in spec["matches"])
        grouped = [
            blocker
            for blocker in blockers
            if blocker not in classified
            and any(
                blocker.endswith(f"::{match}") or f"::{match}" in blocker
                for match in matches
            )
        ]
        classified.update(grouped)
        groups[group_name] = {
            "scope": spec["scope"],
            "description": spec["description"],
            "blocker_count": len(grouped),
            "blockers": grouped,
        }
    unassigned_blockers = [blocker for blocker in blockers if blocker not in classified]
    return {
        "schema_version": "fresh-full-validation-blocker-groups.v1",
        "grouping_policy": (
            "Preserve every lane blocker while separating publication boundary, "
            "fresh receipt presence, receipt metadata/freshness, receipt identity, "
            "schema validation, and artifact integrity failures."
        ),
        "blocker_count": len(blockers),
        "unassigned_blocker_count": len(unassigned_blockers),
        "unassigned_blockers": unassigned_blockers,
        "groups": groups,
    }


def _lane_scope(row: dict[str, Any]) -> str:
    lane_id = str(row.get("lane_id", ""))
    if lane_id == "gpu_hip_solver":
        return "performance_track_after_cpu_reference_parity"
    if lane_id in {"commercial_benchmark_torch", "external_benchmark_refresh"}:
        return "benchmark_validation_refresh"
    if lane_id in {"performance_profile", "productization_heavy_profile"}:
        return "performance_or_heavy_profile_refresh"
    return "fresh_full_validation_refresh"


def _lane_boundary_metadata(rows: list[dict[str, Any]]) -> dict[str, Any]:
    lanes: dict[str, dict[str, Any]] = {}
    for row in rows:
        lane_id = str(row.get("lane_id", ""))
        lanes[lane_id] = {
            "runner": str(row.get("runner", "")),
            "scope": _lane_scope(row),
            "pass": bool(row.get("pass") is True),
            "fresh_validation_receipt": str(row.get("fresh_validation_receipt", "")),
            "blockers": list(row.get("blockers", [])),
        }
    return {
        "schema_version": "fresh-full-validation-lane-boundaries.v1",
        "gpu_hip_policy": (
            "GPU/HIP validation remains a performance-track lane after CPU reference "
            "parity. Missing GPU/HIP fresh receipts must stay visible and must not be "
            "used to replace CPU full-load/full-mesh/material-Newton closure evidence."
        ),
        "lanes": lanes,
    }


def _lane_row(
    lane: dict[str, Any],
    *,
    docs_text: str,
    receipt_root: Path,
    receipt_schema: dict[str, Any],
) -> dict[str, Any]:
    lane_id = str(lane["lane_id"])
    materialized_paths = [Path(path) for path in lane.get("materialized_paths", [])]
    doc_terms = [str(term) for term in lane.get("doc_terms", [])]
    receipt_path = receipt_root / f"{lane_id}.fresh_validation_receipt.json"
    receipt_payload = _load_json(receipt_path)
    materialized_present = all(path.exists() for path in materialized_paths)
    doc_boundary_present = all(term.lower() in docs_text for term in doc_terms)
    receipt_present = receipt_path.exists()
    receipt_metadata_present = _has_metadata(receipt_payload)
    receipt_reused_evidence = receipt_payload.get("reused_evidence")
    receipt_fresh = receipt_present and receipt_reused_evidence is False
    receipt_self_asserted = _truthy_contract(receipt_payload)
    receipt_lane_matches = receipt_present and receipt_payload.get("lane_id") == lane_id
    receipt_runner_matches = receipt_present and receipt_payload.get("runner") == str(lane.get("runner", ""))
    validation = _validate_receipt(receipt_path, receipt_schema) if receipt_present else {
        "contract_pass": False,
        "reason_code": "ERR_FRESH_VALIDATION_RECEIPT_INVALID",
        "blockers": ["fresh_validation_receipt_missing"],
    }
    receipt_validator_pass = bool(validation.get("contract_pass"))
    receipt_validator_blockers = list(validation.get("blockers", []))
    artifact_integrity = (
        _receipt_artifact_integrity_check(receipt_payload, receipt_path=receipt_path)
        if receipt_present and receipt_validator_pass
        else {"blockers": [], "path_aliases": []}
    )
    artifact_integrity_blockers = list(artifact_integrity["blockers"])
    artifact_path_aliases = list(artifact_integrity["path_aliases"])
    receipt_artifact_integrity_pass = receipt_present and not artifact_integrity_blockers
    lane_pass = bool(
        materialized_present
        and doc_boundary_present
        and receipt_present
        and receipt_metadata_present
        and receipt_fresh
        and receipt_self_asserted
        and receipt_validator_pass
        and receipt_artifact_integrity_pass
        and receipt_lane_matches
        and receipt_runner_matches
    )
    blockers = [
        *(["materialized_publication_evidence_missing"] if not materialized_present else []),
        *(["validation_lane_boundary_missing_from_docs"] if not doc_boundary_present else []),
        *(["fresh_validation_receipt_missing"] if not receipt_present else []),
        *(["fresh_validation_receipt_metadata_missing"] if receipt_present and not receipt_metadata_present else []),
        *(["fresh_validation_receipt_reuses_evidence"] if receipt_present and not receipt_fresh else []),
        *(["fresh_validation_receipt_not_green"] if receipt_present and not receipt_self_asserted else []),
        *(["fresh_validation_receipt_lane_mismatch"] if receipt_present and not receipt_lane_matches else []),
        *(["fresh_validation_receipt_runner_mismatch"] if receipt_present and not receipt_runner_matches else []),
        *(
            ["fresh_validation_receipt_invalid"]
            if receipt_present and not receipt_validator_pass
            else []
        ),
        *(
            [f"fresh_validation_receipt_invalid:{blocker}" for blocker in receipt_validator_blockers]
            if receipt_present and not receipt_validator_pass
            else []
        ),
        *(
            ["fresh_validation_receipt_artifact_integrity_failed"]
            if artifact_integrity_blockers
            else []
        ),
        *[
            f"fresh_validation_receipt_artifact_integrity_failed:{blocker}"
            for blocker in artifact_integrity_blockers
        ],
    ]
    return {
        "lane_id": lane_id,
        "runner": str(lane.get("runner", "")),
        "materialized_paths": [str(path) for path in materialized_paths],
        "materialized_publication_evidence_present": materialized_present,
        "doc_terms": doc_terms,
        "validation_lane_boundary_present": doc_boundary_present,
        "fresh_validation_receipt": str(receipt_path),
        "fresh_validation_receipt_present": receipt_present,
        "fresh_validation_receipt_metadata_present": receipt_metadata_present,
        "fresh_validation_receipt_reused_evidence": receipt_reused_evidence,
        "fresh_validation_receipt_fresh": receipt_fresh,
        "fresh_validation_receipt_self_asserted": receipt_self_asserted,
        "fresh_validation_receipt_lane_matches": receipt_lane_matches,
        "fresh_validation_receipt_runner_matches": receipt_runner_matches,
        "fresh_validation_receipt_contract_pass": receipt_validator_pass,
        "fresh_validation_receipt_artifact_integrity_pass": receipt_artifact_integrity_pass,
        "fresh_validation_receipt_artifact_integrity_blockers": artifact_integrity_blockers,
        "fresh_validation_receipt_path_alias_count": len(artifact_path_aliases),
        "fresh_validation_receipt_path_aliases": artifact_path_aliases,
        "fresh_validation_receipt_reason_code": validation.get("reason_code"),
        "fresh_validation_receipt_blockers": receipt_validator_blockers,
        "pass": lane_pass,
        "blockers": blockers,
    }


def build_status(
    *,
    docs: tuple[Path, ...] = DEFAULT_DOCS,
    receipt_root: Path = DEFAULT_RECEIPT_ROOT,
    lanes: tuple[dict[str, Any], ...] = DEFAULT_LANES,
    receipt_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    docs_text = _read_docs(docs)
    schema = receipt_schema if receipt_schema is not None else _load_receipt_schema()
    rows = [
        _lane_row(lane, docs_text=docs_text, receipt_root=receipt_root, receipt_schema=schema)
        for lane in lanes
    ]
    blockers = [f"{row['lane_id']}::{blocker}" for row in rows for blocker in row["blockers"]]
    lane_contract_blockers = [
        f"{row['lane_id']}::{blocker}"
        for row in rows
        for blocker in row["blockers"]
        if blocker in {"materialized_publication_evidence_missing", "validation_lane_boundary_missing_from_docs"}
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                *docs,
                *[path for lane in lanes for path in lane.get("materialized_paths", [])],
                receipt_root,
                DEFAULT_RECEIPT_SCHEMA,
            ],
            reused_evidence=True,
            reuse_policy="status_rebuilt_from_docs_materialized_evidence_and_optional_fresh_validation_receipts",
        ),
        "status": "ready" if not blockers else "blocked",
        "contract_pass": not blockers,
        "lane_contract_pass": not lane_contract_blockers,
        "fresh_full_validation_ready": not blockers,
        "reason_code": "PASS" if not blockers else "ERR_FRESH_FULL_VALIDATION_LANES_INCOMPLETE",
        "receipt_root": str(receipt_root),
        "receipt_schema": str(DEFAULT_RECEIPT_SCHEMA),
        "summary": {
            "lane_count": len(rows),
            "lane_pass_count": sum(1 for row in rows if row["pass"]),
            "lane_contract_pass_count": sum(
                1
                for row in rows
                if row["materialized_publication_evidence_present"] and row["validation_lane_boundary_present"]
            ),
            "fresh_validation_receipt_present_count": sum(
                1 for row in rows if row["fresh_validation_receipt_present"]
            ),
            "fresh_validation_receipt_pass_count": sum(
                1
                for row in rows
                if row["pass"]
            ),
            "fresh_validation_receipt_path_alias_count": sum(
                int(row["fresh_validation_receipt_path_alias_count"]) for row in rows
            ),
            "blocker_count": len(blockers),
        },
        "rows": rows,
        "blockers": blockers,
        "blocker_grouping_metadata": _fresh_validation_blocker_grouping_metadata(blockers),
        "lane_boundary_metadata": _lane_boundary_metadata(rows),
        "claim_boundary": (
            "This status separates release publication materialization from fresh full-validation. "
            "A release evidence freshness PASS only proves metadata/source recency. Level 3 promotion "
            "still requires fresh validation receipts for each named lane, with reused_evidence=false, "
            "validated by implementation/phase1/validate_fresh_validation_receipt.py. Missing or invalid "
            "receipts must stay blocked and must not be replaced by CPU-required hydrated reports. Legacy "
            "path aliases resolve only tracked release-evidence migrations and pass only when the resolved "
            "file sha256 matches the receipt expectation."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Fresh Full-Validation Lane Status",
        "",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `lane_contract_pass`: `{payload['lane_contract_pass']}`",
        f"- `fresh_full_validation_ready`: `{payload['fresh_full_validation_ready']}`",
        f"- `blockers`: `{len(payload['blockers'])}`",
        "",
        "| Lane | Materialized Evidence | Fresh Receipt | Status |",
        "|---|---|---|---|",
    ]
    for row in payload["rows"]:
        lines.append(
            f"| `{row['lane_id']}` | `{row['materialized_publication_evidence_present']}` | "
            f"`{row['fresh_validation_receipt_present']}` | `{'pass' if row['pass'] else 'blocked'}` |"
        )
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-root", type=Path, default=DEFAULT_RECEIPT_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_status(receipt_root=args.receipt_root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        if args.json
        else (
            "fresh-full-validation-lanes: "
            f"{'PASS' if payload['contract_pass'] else 'BLOCKED'} | "
            f"lanes={payload['summary']['lane_pass_count']}/{payload['summary']['lane_count']} | "
            f"receipts={payload['summary']['fresh_validation_receipt_pass_count']}/"
            f"{payload['summary']['lane_count']} | blockers={payload['summary']['blocker_count']}"
        )
    )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
