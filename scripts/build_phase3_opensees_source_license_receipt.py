#!/usr/bin/env python3
"""Build a Phase 3 OpenSees medium source/license receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "phase3_opensees_medium_source_license_receipt.json"
OPEN_SEES_INPUTS = [
    Path("implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl"),
    Path("implementation/phase1/open_data/megastructure/opensees/SCBF16B.tcl"),
    Path("implementation/phase1/opensees_topology_report.json"),
    Path("implementation/phase1/release/benchmark_expansion/opensees_canonical_breadth_report.json"),
    Path("src/structural_analysis/benchmark/acquisition.py"),
    Path("scripts/build_phase3_opensees_source_license_receipt.py"),
]
LOCAL_SHA256_CHECK_SNIPPET = (
    "from pathlib import Path; "
    "import hashlib; "
    "import sys; "
    "actual = hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest(); "
    "raise SystemExit(0 if actual == sys.argv[2] else 1)"
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def _canonical_rows(canonical_report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = canonical_report.get("rows")
    if not isinstance(rows, list):
        return []
    wanted = {"SCBF16B", "SCBF16B_shell_beam_mix"}
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("case_id") not in wanted:
            continue
        result.append(
            {
                "case_id": row.get("case_id"),
                "family_id": row.get("family_id"),
                "path": row.get("path"),
                "format": row.get("format"),
                "origin": row.get("origin"),
                "size_bytes": row.get("size_bytes"),
                "sha256": row.get("sha256"),
                "parser_contract_ready": bool(row.get("parser_contract_ready")),
            }
        )
    return sorted(result, key=lambda row: str(row.get("case_id")))


def _local_candidate_verification_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    verification_rows: list[dict[str, Any]] = []
    for row in rows:
        path = str(row.get("path", ""))
        sha256 = str(row.get("sha256", ""))
        verification_rows.append(
            {
                "case_id": row.get("case_id"),
                "path": path,
                "expected_sha256": sha256,
                "verification_command": [
                    "python3",
                    "-c",
                    LOCAL_SHA256_CHECK_SNIPPET,
                    path,
                    sha256,
                ],
            }
        )
    return verification_rows


def build_phase3_opensees_source_license_receipt(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    topology_report = _load_json(repo_root / "implementation/phase1/opensees_topology_report.json")
    canonical_report = _load_json(
        repo_root / "implementation/phase1/release/benchmark_expansion/opensees_canonical_breadth_report.json"
    )
    local_candidate_artifacts = _canonical_rows(canonical_report)
    topology_source = topology_report.get("source_provenance")
    topology_source = topology_source if isinstance(topology_source, dict) else {}
    topology_metrics = topology_report.get("metrics")
    topology_metrics = topology_metrics if isinstance(topology_metrics, dict) else {}
    topology_checks = topology_report.get("checks")
    topology_checks = topology_checks if isinstance(topology_checks, dict) else {}
    blockers = [
        "authoritative_source_url_missing",
        "upstream_license_text_missing",
        "redistribution_rights_unverified",
        "commercial_use_rights_unverified",
        "authoritative_download_or_acquisition_script_blocked_source_url_missing",
        "reference_outputs_missing",
        "normalization_not_implemented",
        "opensees_medium_scorecard_execution_missing",
    ]
    topology_contract_pass = bool(topology_report.get("contract_pass"))
    local_checksum_attached = len(local_candidate_artifacts) == 2 and all(
        str(row.get("sha256", "")).strip()
        for row in local_candidate_artifacts
    )
    return {
        "schema_version": "phase3-opensees-medium-source-license-receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha or git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(OPEN_SEES_INPUTS, repo_root=repo_root),
        "source_id": "opensees_scbf16b_medium_candidate",
        "lanes": ["opensees-medium"],
        "status": "blocked",
        "contract_pass": False,
        "phase3_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "source_url_verified": False,
        "license_review_status": "blocked_no_authoritative_license_source_attached",
        "redistribution_allowed": False,
        "commercial_use_allowed": False,
        "local_candidate_checksum_attached": local_checksum_attached,
        "local_candidate_artifacts": local_candidate_artifacts,
        "authoritative_acquisition": {
            "status": "blocked_source_url_and_license_missing",
            "source_url_verified": False,
            "download_command": [],
            "blockers": [
                "authoritative_source_url_missing",
                "upstream_license_text_missing",
                "authoritative_download_or_acquisition_script_blocked_source_url_missing",
            ],
            "claim_boundary": (
                "No authoritative upstream source URL or license text is attached, so this "
                "receipt deliberately does not author a download command for OpenSees medium."
            ),
        },
        "local_candidate_verification": {
            "status": "ready_for_local_parser_work_only",
            "contract_pass": local_checksum_attached and topology_contract_pass,
            "checksum_verification_rows": _local_candidate_verification_rows(local_candidate_artifacts),
            "topology_verification_command": [
                "python3",
                "scripts/build_phase3_opensees_source_license_receipt.py",
                "--check",
            ],
            "claim_boundary": (
                "These commands verify only committed/local candidate checksums and topology "
                "receipt consistency. They do not prove upstream source authority, license "
                "permission, reference outputs, normalization, or OpenSees medium scorecard execution."
            ),
        },
        "topology_receipt": {
            "path": "implementation/phase1/opensees_topology_report.json",
            "contract_pass": topology_contract_pass,
            "source_path": topology_source.get("source_path"),
            "source_sha256": topology_source.get("source_sha256"),
            "node_count": topology_metrics.get("node_count"),
            "beam_element_count": topology_metrics.get("beam_element_count"),
            "shell_element_count": topology_metrics.get("shell_element_count"),
            "source_is_opensees_text": bool(topology_checks.get("source_is_opensees_text")),
            "real_topology_pass": bool(topology_checks.get("real_topology_pass")),
            "shell_beam_mix_pass": bool(topology_checks.get("shell_beam_mix_pass")),
            "claim_boundary": (
                "Topology receipt proves local parser/topology checks only. It does not prove "
                "source URL authority, license permission, reference outputs, normalization, "
                "solver accuracy, or Phase 3 quantity credit."
            ),
        },
        "source_url_candidates": [],
        "license_evidence": {
            "license_text_path": "",
            "spdx": "",
            "review_owner": "",
            "review_status": "missing",
            "claim_boundary": (
                "No authoritative upstream license text is attached to this receipt. "
                "Local files and checksums cannot be treated as redistribution approval."
            ),
        },
        "blockers": blockers,
        "claim_boundary": (
            "This receipt separates local OpenSees medium candidate checksum/topology evidence "
            "from source and license approval. It keeps source URL verification, license review, "
            "redistribution, commercial use, reference outputs, normalization, and scorecard "
            "execution for OpenSees medium blocked. It does not close OpenSees medium, "
            "Developer Preview RC, or Phase 3."
        ),
    }


def write_phase3_opensees_source_license_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = build_phase3_opensees_source_license_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase3_opensees_source_license_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> tuple[bool, str]:
    expected = build_phase3_opensees_source_license_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase3_opensees_source_license_missing:{out_path.as_posix()}"
    try:
        existing = _load_json(resolved)
    except Exception as exc:
        return False, f"phase3_opensees_source_license_unreadable:{out_path.as_posix()}:{exc.__class__.__name__}"
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase3_opensees_source_license_mismatch"
    return True, "phase3_opensees_source_license_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--source-commit-sha", default=None)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_phase3_opensees_source_license_receipt(
            out_path=args.out,
            source_commit_sha=args.source_commit_sha,
        )
        print(f"Phase 3 OpenSees source/license check: {message}")
        return 0 if ok else 1
    payload = write_phase3_opensees_source_license_receipt(
        out_path=args.out,
        source_commit_sha=args.source_commit_sha,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "Phase 3 OpenSees source/license receipt: "
            f"{payload['status']} | source_url_verified={payload['source_url_verified']} | "
            f"local_checksum={payload['local_candidate_checksum_attached']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
