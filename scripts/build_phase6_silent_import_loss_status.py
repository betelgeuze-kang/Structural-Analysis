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
BLOCKER_GROUP_SCHEMA_VERSION = "phase6-silent-import-loss-blocker-groups.v1"
BLOCKER_GROUPS = {
    "source_acquisition": {
        "display_name": "source/acquisition",
        "scope": "direct_silent_import_loss",
        "blockers": {
            "source_file_not_acquired",
            "phase3_ifc_import_case_count_below_minimum",
        },
    },
    "checksum": {
        "display_name": "checksum",
        "scope": "direct_silent_import_loss",
        "blockers": {
            "source_sha256_missing",
            "selected_file_checksums_missing",
        },
    },
    "license_legal": {
        "display_name": "license/legal",
        "scope": "direct_silent_import_loss",
        "blockers": {
            "phase3_ifc_source_license_review_counts_missing",
            "product_legal_license_review_pending",
            "per_file_license_review_pending",
        },
        "prefixes": (
            "phase3_ifc_source_license_review_blockers_not_cleared:",
        ),
    },
    "quantity_credit": {
        "display_name": "quantity credit",
        "scope": "direct_silent_import_loss",
        "blockers": {
            "phase3_ifc_source_license_quantity_credit_count_missing",
            "phase3_ifc_import_case_quantity_credit_blocked_pending_license_review",
            "phase3_ifc_import_case_quantity_credit_missing",
        },
        "prefixes": (
            "phase3_ifc_source_license_quantity_credit_below_required:",
        ),
    },
    "import_execution": {
        "display_name": "import execution",
        "scope": "direct_silent_import_loss",
        "blockers": {
            "dirty_import_execution_missing",
            "import_health_execution_missing",
        },
        "prefixes": (
            "ifc_import_health_execution_count_below_required:",
        ),
    },
    "silent_loss_gate": {
        "display_name": "silent-loss gate",
        "scope": "direct_silent_import_loss",
        "blockers": {
            "silent_data_loss_negative_gate_not_executed",
            "silent_import_loss_gate_not_executed",
            "silent_import_loss_gate_not_implemented",
        },
    },
    "query_gui_spillover": {
        "display_name": "query/gui spillover",
        "scope": "spillover_not_direct_silent_import_loss",
        "blockers": {
            "dataset_repository_url_missing",
            "gui_task_runner_not_implemented",
            "query_expected_answers_missing",
            "query_task_file_checksums_missing",
        },
    },
}


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


def _blocker_matches_group(blocker: str, group: dict[str, Any]) -> bool:
    if blocker in group.get("blockers", set()):
        return True
    return any(blocker.startswith(prefix) for prefix in group.get("prefixes", ()))


def _blocker_grouping_metadata(blockers: list[str]) -> dict[str, Any]:
    grouped_blockers: set[str] = set()
    groups: dict[str, dict[str, Any]] = {}
    for group_id, group in BLOCKER_GROUPS.items():
        group_blockers = [
            blocker for blocker in blockers if _blocker_matches_group(blocker, group)
        ]
        grouped_blockers.update(group_blockers)
        groups[group_id] = {
            "display_name": group["display_name"],
            "scope": group["scope"],
            "blocked": bool(group_blockers),
            "blockers": group_blockers,
        }
    return {
        "schema_version": BLOCKER_GROUP_SCHEMA_VERSION,
        "claim_boundary": (
            "Query/GUI spillover blockers are carried through for visibility from the "
            "Phase 3 source-license receipt, but they are not direct silent-import-loss "
            "closure blockers and are excluded from the direct RC gate blocker list. "
            "The RC gate remains blocked until the direct source, checksum, license, "
            "quantity-credit, import execution, and silent-loss gate groups are clear."
        ),
        "groups": groups,
        "unassigned_blockers": [
            blocker for blocker in blockers if blocker not in grouped_blockers
        ],
    }


def _direct_and_spillover_blockers(blockers: list[str]) -> tuple[list[str], list[str]]:
    direct: list[str] = []
    spillover: list[str] = []
    query_group = BLOCKER_GROUPS["query_gui_spillover"]
    for blocker in blockers:
        if _blocker_matches_group(blocker, query_group):
            spillover.append(blocker)
        else:
            direct.append(blocker)
    return sorted(dict.fromkeys(direct)), sorted(dict.fromkeys(spillover))


def _group_blockers(blockers: list[str], group_ids: set[str]) -> list[str]:
    selected: list[str] = []
    for blocker in blockers:
        if any(_blocker_matches_group(blocker, BLOCKER_GROUPS[group_id]) for group_id in group_ids):
            selected.append(blocker)
    return sorted(dict.fromkeys(selected))


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
    source_file_acquired_count = int(
        import_health.get("source_file_acquired_count", 0)
        or int(clean_acquisition.get("source_file_acquired_count", 0) or 0)
        + int(dirty_acquisition.get("source_file_acquired_count", 0) or 0)
    )
    source_checksum_attached_count = int(
        import_health.get("source_checksum_attached_count", 0)
        or int(clean_acquisition.get("source_checksum_attached_count", 0) or 0)
        + int(dirty_acquisition.get("source_checksum_attached_count", 0) or 0)
    )
    visible_entity_accounting_case_count = int(
        import_health.get("visible_entity_accounting_case_count", 0) or 0
    )
    silent_import_loss_gate_pass_count = int(
        import_health.get("silent_import_loss_gate_pass_count", 0) or 0
    )
    quantity_credit_ready_count = int(
        import_health.get("quantity_credit_ready_count", 0) or 0
    )
    source_blockers = _blockers(source_license)
    acquisition_blockers = _blockers(clean_acquisition, dirty_acquisition)
    import_health_blockers = _blockers(import_health)
    source_acquired = source_file_acquired_count >= REQUIRED_IFC_IMPORT_CASE_COUNT
    checksums_ready = source_checksum_attached_count >= REQUIRED_IFC_IMPORT_CASE_COUNT
    source_license_receipt_contract_pass = source_license.get("contract_pass") is True
    source_license_review_blocker_count = _optional_int(
        source_license.get("source_license_review_blocker_count")
    )
    source_license_review_pass_count = _optional_int(
        source_license.get("source_license_review_pass_count")
    )
    source_license_quantity_credit_ready_count = _optional_int(
        source_license.get("quantity_credit_ready_count")
    )
    license_blocker_names_clear = not any(
        "license" in blocker or "legal" in blocker for blocker in source_blockers
    )
    source_license_review_ready = bool(
        source_license_review_blocker_count == 0
        and source_license_review_pass_count is not None
        and license_blocker_names_clear
    )
    source_license_quantity_credit_ready = bool(
        source_license_quantity_credit_ready_count is not None
        and source_license_quantity_credit_ready_count >= REQUIRED_IFC_IMPORT_CASE_COUNT
    )
    license_ready = source_license_review_ready
    import_health_ready = bool(
        import_health_execution_count >= REQUIRED_IFC_IMPORT_CASE_COUNT
        and import_health_contract_pass_count >= REQUIRED_IFC_IMPORT_CASE_COUNT
    )
    silent_negative_gate_executed = bool(
        silent_import_loss_gate_pass_count >= REQUIRED_IFC_IMPORT_CASE_COUNT
        and visible_entity_accounting_case_count >= REQUIRED_IFC_IMPORT_CASE_COUNT
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
        "source_license_review_ready": {
            "blocker_count": source_license_review_blocker_count,
            "pass_count": source_license_review_pass_count,
            "contract_pass": source_license_review_ready,
        },
        "source_license_quantity_credit_ready": {
            "current": source_license_quantity_credit_ready_count,
            "required": REQUIRED_IFC_IMPORT_CASE_COUNT,
            "contract_pass": source_license_quantity_credit_ready,
        },
        "source_license_receipt_contract_pass": source_license_receipt_contract_pass,
        "import_health_execution_ready": import_health_ready,
        "silent_data_loss_negative_gate_executed": silent_negative_gate_executed,
    }
    blockers = _blockers(import_health, source_license)
    if source_license_review_blocker_count is None:
        blockers.append("phase3_ifc_source_license_review_counts_missing")
    elif source_license_review_blocker_count:
        blockers.append(
            "phase3_ifc_source_license_review_blockers_not_cleared:"
            f"{source_license_review_blocker_count}"
        )
    if source_license_quantity_credit_ready_count is None:
        blockers.append("phase3_ifc_source_license_quantity_credit_count_missing")
    elif source_license_quantity_credit_ready_count < REQUIRED_IFC_IMPORT_CASE_COUNT:
        blockers.append(
            "phase3_ifc_source_license_quantity_credit_below_required:"
            f"{source_license_quantity_credit_ready_count}/{REQUIRED_IFC_IMPORT_CASE_COUNT}"
        )
    if not source_acquired or not checksums_ready:
        blockers.extend(acquisition_blockers)
    if not import_health_ready:
        blockers.extend(import_health_blockers)
    if not silent_negative_gate_executed:
        blockers.extend(import_health.get("silent_import_loss_gate", {}).get("blockers", []))
    if not case_count_ready:
        blockers.append(
            f"ifc_import_case_count_below_required:{selected_import_case_count}/{REQUIRED_IFC_IMPORT_CASE_COUNT}"
        )
    if import_health_execution_count < REQUIRED_IFC_IMPORT_CASE_COUNT:
        blockers.append(
            f"ifc_import_health_execution_count_below_required:{import_health_execution_count}/{REQUIRED_IFC_IMPORT_CASE_COUNT}"
        )
    all_blockers = sorted(dict.fromkeys(blockers))
    direct_blockers, spillover_blockers = _direct_and_spillover_blockers(all_blockers)
    product_credit_blockers = _group_blockers(
        direct_blockers,
        {"license_legal", "quantity_credit"},
    )
    technical_direct_blockers = [
        blocker for blocker in direct_blockers if blocker not in set(product_credit_blockers)
    ]
    technical_silent_import_loss_zero = bool(
        not technical_direct_blockers
        and case_count_ready
        and source_acquired
        and checksums_ready
        and import_health_ready
        and silent_negative_gate_executed
    )
    product_release_credit_ready = bool(
        not product_credit_blockers
        and license_ready
        and quantity_credit_ready_count >= REQUIRED_IFC_IMPORT_CASE_COUNT
        and source_license_quantity_credit_ready
    )
    contract_pass = bool(
        not direct_blockers
        and case_count_ready
        and source_acquired
        and checksums_ready
        and license_ready
        and source_license_quantity_credit_ready
        and import_health_ready
        and silent_negative_gate_executed
    )
    owner_actions = []
    if not source_acquired or not checksums_ready:
        owner_actions.append("acquire/checksum all selected clean/dirty IFC source files")
    if not import_health_ready or not silent_negative_gate_executed:
        owner_actions.append("regenerate Phase 3 import-health and silent-data-loss receipts")
    if not license_ready or quantity_credit_ready_count < REQUIRED_IFC_IMPORT_CASE_COUNT:
        owner_actions.append("complete product/legal and per-file license review for quantity credit")
    if any(
        blocker
        in {
            "dataset_repository_url_missing",
            "gui_task_runner_not_implemented",
            "query_expected_answers_missing",
            "query_task_file_checksums_missing",
        }
        for blocker in all_blockers
    ):
        owner_actions.append("close or explicitly defer the ifc-bench query/GUI spillover blockers")
    owner_action = "; ".join(owner_actions) + "; then refresh the RC final gate."
    if contract_pass:
        owner_action = "Silent-import-loss evidence is ready; refresh the RC final gate."
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
        "technical_silent_import_loss_zero": technical_silent_import_loss_zero,
        "technical_direct_blockers": technical_direct_blockers,
        "product_release_credit_ready": product_release_credit_ready,
        "product_release_credit_blockers": product_credit_blockers,
        "required_ifc_import_case_count": REQUIRED_IFC_IMPORT_CASE_COUNT,
        "clean_selected_file_count": clean_selected_file_count,
        "dirty_selected_file_count": dirty_selected_file_count,
        "selected_import_case_count": selected_import_case_count,
        "source_file_acquired_count": source_file_acquired_count,
        "source_checksum_attached_count": source_checksum_attached_count,
        "import_health_execution_count": import_health_execution_count,
        "import_health_contract_pass_count": import_health_contract_pass_count,
        "visible_entity_accounting_case_count": visible_entity_accounting_case_count,
        "silent_import_loss_gate_pass_count": silent_import_loss_gate_pass_count,
        "quantity_credit_ready_count": quantity_credit_ready_count,
        "source_license_receipt_contract_pass": source_license_receipt_contract_pass,
        "source_license_review_blocker_count": source_license_review_blocker_count,
        "source_license_review_pass_count": source_license_review_pass_count,
        "source_license_quantity_credit_ready_count": source_license_quantity_credit_ready_count,
        "silent_import_loss_zero": technical_silent_import_loss_zero,
        "evidence_requirements": {
            **evidence_requirements,
            "technical_silent_import_loss_zero": technical_silent_import_loss_zero,
            "product_release_credit_ready": product_release_credit_ready,
        },
        "readiness_inputs": {
            "import_health_receipt": PHASE3_IFC_IMPORT_HEALTH.as_posix(),
            "clean_acquisition_receipt": PHASE3_IFC_CLEAN_ACQUISITION.as_posix(),
            "dirty_acquisition_receipt": PHASE3_IFC_DIRTY_ACQUISITION.as_posix(),
            "source_license_receipt": PHASE3_IFC_SOURCE_LICENSE.as_posix(),
        },
        "blockers": direct_blockers,
        "direct_blockers": direct_blockers,
        "spillover_blockers": spillover_blockers,
        "all_blockers": all_blockers,
        "blocker_grouping_metadata": _blocker_grouping_metadata(all_blockers),
        "owner_action": owner_action,
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
            "review, import-health execution, and silent-data-loss negative gates all pass. "
            "Query/GUI corpus readiness is reported separately as spillover evidence and "
            "does not by itself block the direct silent-import-loss final gate. The "
            "technical_silent_import_loss_zero field is scoped to acquired/checksummed "
            "sources plus executed import-health and negative silent-loss gates; product "
            "license review and quantity credit remain separate release/product-credit "
            "requirements."
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
