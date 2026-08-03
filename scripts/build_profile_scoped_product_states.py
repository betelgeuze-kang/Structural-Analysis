#!/usr/bin/env python3
"""Build profile-scoped Developer Preview and commercial product states.

The Developer Preview state consumes only Developer Preview evidence. Commercial,
GPU, customer, license, and SLA blockers remain visible as future gates but cannot
make the Developer Preview schema invalid. The commercial state remains fail-closed
on the existing PM release report and its source-provenance guard.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DP_STATUS = (
    ROOT
    / "implementation/phase1/release_evidence/productization/developer_preview_rc_status.json"
)
DEFAULT_PM_REPORT = (
    ROOT
    / "implementation/phase1/release_evidence/productization/pm_release_gate_report.json"
)


class ProfileScopedStateError(RuntimeError):
    """Raised when a source product-state artifact is unavailable or malformed."""


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProfileScopedStateError(f"invalid_json:{path}") from error
    if not isinstance(payload, dict):
        raise ProfileScopedStateError(f"json_not_object:{path}")
    return payload


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _serialized(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as handle:
        handle.write(_serialized(payload))
        temporary = Path(handle.name)
    temporary.replace(path)


def build_developer_preview_state(
    *,
    source_commit_sha: str,
    developer_preview_status: Path,
) -> dict[str, Any]:
    rc = _load_object(developer_preview_status)
    blockers = [str(item) for item in rc.get("blockers", [])]
    final_gates = [row for row in rc.get("final_gates", []) if isinstance(row, dict)]
    deliverables = [row for row in rc.get("deliverables", []) if isinstance(row, dict)]
    state_ready = bool(
        rc.get("developer_preview_ready")
        or rc.get("developer_preview_release_candidate_ready")
    )
    return {
        "schema_version": "developer-preview-product-state.v1",
        "source_commit_sha": source_commit_sha,
        "target_profile": "planar_frame_verified_alpha.v1",
        "contract_pass": True,
        "state_ready": state_ready,
        "status": "ready" if state_ready else "blocked",
        "public": True,
        "release_eligible": False,
        "deliverable_count": int(rc.get("deliverable_count", len(deliverables))),
        "deliverable_pass_count": int(
            rc.get(
                "deliverable_pass_count",
                sum(1 for row in deliverables if row.get("contract_pass") is True),
            )
        ),
        "final_gate_count": int(rc.get("final_gate_count", len(final_gates))),
        "final_gate_pass_count": int(
            rc.get(
                "final_gate_pass_count",
                sum(1 for row in final_gates if row.get("contract_pass") is True),
            )
        ),
        "blockers": blockers,
        "future_commercial_gates": [
            str(item) for item in rc.get("future_commercial_gates", [])
        ],
        "commercial_inputs_consumed": [],
        "inputs": {
            "developer_preview_status": developer_preview_status.as_posix(),
            "developer_preview_status_sha256": _sha256(developer_preview_status),
        },
        "claim_boundary": (
            "This state evaluates the bounded public Developer Preview only. "
            "Customer shadow, product license, license-server operation, SLA, "
            "independent commercial-product readiness, GPU residency, and general "
            "solver breadth remain future gates and do not invalidate this schema."
        ),
    }


def build_commercial_state(
    *,
    source_commit_sha: str,
    pm_report: Path,
) -> dict[str, Any]:
    report = _load_object(pm_report)
    provenance = report.get("source_input_provenance")
    provenance_pass = bool(
        isinstance(provenance, dict) and provenance.get("contract_pass") is True
    )
    state_ready = bool(
        report.get("full_release_gate_ready") is True
        and report.get("release_claims_fail_closed") is not True
        and provenance_pass
    )
    return {
        "schema_version": "commercial-release-product-state.v1",
        "source_commit_sha": source_commit_sha,
        "target_profile": "limited_commercial_structural_solver",
        "contract_pass": True,
        "state_ready": state_ready,
        "status": "ready" if state_ready else "blocked",
        "blockers": [str(item) for item in report.get("full_release_blockers", [])],
        "source_provenance_contract_pass": provenance_pass,
        "release_claims_fail_closed": bool(
            report.get("release_claims_fail_closed") is True
        ),
        "release_tiers": report.get("release_tiers", {}),
        "inputs": {
            "pm_release_report": pm_report.as_posix(),
            "pm_release_report_sha256": _sha256(pm_report),
        },
        "claim_boundary": (
            "This state evaluates the commercial release track only. It consumes the "
            "fail-closed PM report and cannot promote Developer Preview completion, "
            "independent V&V, customer evidence, license approval, or GPU production "
            "readiness that is absent from the declared inputs."
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument(
        "--developer-preview-status",
        type=Path,
        default=DEFAULT_DP_STATUS,
    )
    parser.add_argument("--pm-report", type=Path, default=DEFAULT_PM_REPORT)
    parser.add_argument("--developer-preview-out", type=Path, required=True)
    parser.add_argument("--commercial-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if len(args.source_commit) != 40 or any(
        character not in "0123456789abcdef" for character in args.source_commit
    ):
        raise ProfileScopedStateError("source_commit_sha_invalid")
    dp = build_developer_preview_state(
        source_commit_sha=args.source_commit,
        developer_preview_status=args.developer_preview_status,
    )
    commercial = build_commercial_state(
        source_commit_sha=args.source_commit,
        pm_report=args.pm_report,
    )
    _write_json(args.developer_preview_out, dp)
    _write_json(args.commercial_out, commercial)
    if args.json:
        print(
            _serialized(
                {
                    "developer_preview": dp,
                    "commercial_release": commercial,
                }
            ),
            end="",
        )
    else:
        print(
            "profile-scoped product states: "
            f"developer_preview={dp['status']} | commercial={commercial['status']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
