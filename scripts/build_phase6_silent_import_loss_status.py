#!/usr/bin/env python3
"""Build a conservative Phase 6 silent-import-loss status receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "phase6_silent_import_loss_status.json"
PHASE3_IFC_IMPORT_HEALTH = PRODUCTIZATION / "phase3_ifc_import_health_execution_receipt.json"
PHASE3_IFC_CLEAN_ACQUISITION = PRODUCTIZATION / "phase3_buildingsmart_ifc_acquisition_receipt.json"
PHASE3_IFC_DIRTY_ACQUISITION = PRODUCTIZATION / "phase3_buildingsmart_dirty_ifc_acquisition_receipt.json"
PHASE3_IFC_SOURCE_LICENSE = PRODUCTIZATION / "phase3_ifc_source_license_receipt.json"
SCHEMA_VERSION = "phase6-silent-import-loss-status.v1"
REQUIRED_IFC_IMPORT_CASE_COUNT = 10


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


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _blockers(*payloads: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for payload in payloads:
        blockers.extend(str(blocker) for blocker in payload.get("blockers", []) if str(blocker))
    return sorted(dict.fromkeys(blockers))


def _selected_count(payload: dict[str, Any]) -> int:
    return int(payload.get("selected_file_count", 0) or 0)


def build_phase6_silent_import_loss_status(*, repo_root: Path = ROOT) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    import_health = _load_json(repo_root, PHASE3_IFC_IMPORT_HEALTH)
    clean_acquisition = _load_json(repo_root, PHASE3_IFC_CLEAN_ACQUISITION)
    dirty_acquisition = _load_json(repo_root, PHASE3_IFC_DIRTY_ACQUISITION)
    source_license = _load_json(repo_root, PHASE3_IFC_SOURCE_LICENSE)
    clean_selected_file_count = _selected_count(clean_acquisition)
    dirty_selected_file_count = _selected_count(dirty_acquisition)
    selected_import_case_count = clean_selected_file_count + dirty_selected_file_count
    import_health_execution_count = int(
        import_health.get("import_health_execution_count", 0) or 0
    )
    import_health_contract_pass_count = int(
        import_health.get("import_health_contract_pass_count", 0) or 0
    )
    source_blockers = _blockers(source_license)
    all_ifc_blockers = _blockers(import_health, clean_acquisition, dirty_acquisition, source_license)
    source_acquired = not any("source_file_not_acquired" in blocker for blocker in all_ifc_blockers)
    checksums_ready = not any(
        "checksum" in blocker or "sha256" in blocker for blocker in all_ifc_blockers
    )
    license_ready = not any("license" in blocker or "legal" in blocker for blocker in source_blockers)
    import_health_ready = bool(import_health.get("contract_pass") is True)
    silent_negative_gate_executed = not any(
        "silent_data_loss_negative_gate_not_executed" in blocker
        or "silent_import_loss_gate_not_executed" in blocker
        or "silent_import_loss_gate_not_implemented" in blocker
        for blocker in all_ifc_blockers
    )
    case_count_ready = selected_import_case_count >= REQUIRED_IFC_IMPORT_CASE_COUNT
    evidence_requirements = {
        "clean_dirty_import_case_count": {
            "current": selected_import_case_count,
            "required": REQUIRED_IFC_IMPORT_CASE_COUNT,
            "contract_pass": case_count_ready,
        },
        "source_files_acquired": source_acquired,
        "selected_file_checksums_ready": checksums_ready,
        "product_license_review_ready": license_ready,
        "import_health_execution_ready": import_health_ready,
        "silent_data_loss_negative_gate_executed": silent_negative_gate_executed,
    }
    blockers = _blockers(import_health, clean_acquisition, dirty_acquisition, source_license)
    if not case_count_ready:
        blockers.append(
            f"ifc_import_case_count_below_required:{selected_import_case_count}/{REQUIRED_IFC_IMPORT_CASE_COUNT}"
        )
    if import_health_execution_count < REQUIRED_IFC_IMPORT_CASE_COUNT:
        blockers.append(
            f"ifc_import_health_execution_count_below_required:{import_health_execution_count}/{REQUIRED_IFC_IMPORT_CASE_COUNT}"
        )
    blockers = sorted(dict.fromkeys(blockers))
    contract_pass = bool(
        not blockers
        and case_count_ready
        and source_acquired
        and checksums_ready
        and license_ready
        and import_health_ready
        and silent_negative_gate_executed
    )
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                PHASE3_IFC_IMPORT_HEALTH,
                PHASE3_IFC_CLEAN_ACQUISITION,
                PHASE3_IFC_DIRTY_ACQUISITION,
                PHASE3_IFC_SOURCE_LICENSE,
                Path("scripts/build_phase6_silent_import_loss_status.py"),
            ],
            reused_evidence=True,
            reuse_policy="phase6_silent_import_loss_status_aggregates_phase3_ifc_receipts",
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "developer_preview_release_candidate_claim": contract_pass,
        "required_ifc_import_case_count": REQUIRED_IFC_IMPORT_CASE_COUNT,
        "clean_selected_file_count": clean_selected_file_count,
        "dirty_selected_file_count": dirty_selected_file_count,
        "selected_import_case_count": selected_import_case_count,
        "import_health_execution_count": import_health_execution_count,
        "import_health_contract_pass_count": import_health_contract_pass_count,
        "evidence_requirements": evidence_requirements,
        "readiness_inputs": {
            "import_health_receipt": PHASE3_IFC_IMPORT_HEALTH.as_posix(),
            "clean_acquisition_receipt": PHASE3_IFC_CLEAN_ACQUISITION.as_posix(),
            "dirty_acquisition_receipt": PHASE3_IFC_DIRTY_ACQUISITION.as_posix(),
            "source_license_receipt": PHASE3_IFC_SOURCE_LICENSE.as_posix(),
        },
        "blockers": blockers,
        "owner_action": (
            "Acquire and checksum the selected clean/dirty IFC files after license review, "
            "execute import-health and silent-data-loss negative gates for every selected "
            "case, then rerun this status before promoting the RC final gate."
        ),
        "summary_line": (
            "Phase 6 silent import loss: "
            f"{'READY' if contract_pass else 'BLOCKED'} | selected="
            f"{selected_import_case_count}/{REQUIRED_IFC_IMPORT_CASE_COUNT} | "
            f"executed={import_health_execution_count}/{REQUIRED_IFC_IMPORT_CASE_COUNT}"
        ),
        "claim_boundary": (
            "This receipt aggregates the current Phase 3 IFC source/license and import-health "
            "receipts for the RC silent-import-loss final gate. It does not download or "
            "bundle IFC files, approve product redistribution, prove import execution, "
            "or prove zero silent import loss until acquired/checksummed sources, license "
            "review, import-health execution, and silent-data-loss negative gates all pass."
        ),
    }


def write_phase6_silent_import_loss_status(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    payload = build_phase6_silent_import_loss_status(repo_root=repo_root)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase6_silent_import_loss_status(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
) -> tuple[bool, str]:
    expected = build_phase6_silent_import_loss_status(repo_root=repo_root)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase6_silent_import_loss_status_missing:{out_path.as_posix()}"
    try:
        existing = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"phase6_silent_import_loss_status_unreadable:{exc.__class__.__name__}"
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase6_silent_import_loss_status_mismatch"
    return True, "phase6_silent_import_loss_status_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_phase6_silent_import_loss_status(out_path=args.out)
        print(f"Phase 6 silent import loss status check: {message}")
        return 0 if ok else 1
    payload = write_phase6_silent_import_loss_status(out_path=args.out)
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
