#!/usr/bin/env python3
"""Build a source-bound technical receipt for the 10-case IFC import-health lane."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_MANIFEST = Path(
    "benchmarks/import_health/buildingsmart_ifc_current_source.v1.json"
)
DEFAULT_SCHEMA = Path(
    "canonical/ifc-import-health-current-source-technical-receipt.v1.schema.json"
)
DEFAULT_ACQUISITION = Path(
    ".ci/ifc-import-health-current-source/acquisition-receipt.json"
)
DEFAULT_OUTPUT = Path(".ci/ifc-import-health-current-source/technical-receipt.json")
DEFAULT_SUPPORT_DIR = Path(".ci/ifc-import-health-current-source/support")
CLEAN_ACQUISITION = PRODUCTIZATION / "phase3_buildingsmart_ifc_acquisition_receipt.json"
DIRTY_ACQUISITION = (
    PRODUCTIZATION / "phase3_buildingsmart_dirty_ifc_acquisition_receipt.json"
)
IMPORT_HEALTH = PRODUCTIZATION / "phase3_ifc_import_health_execution_receipt.json"
SOURCE_LICENSE = PRODUCTIZATION / "phase3_ifc_source_license_receipt.json"
SILENT_IMPORT_LOSS = PRODUCTIZATION / "phase6_silent_import_loss_status.json"
RECEIPT_SCHEMA_VERSION = "ifc-import-health-current-source-technical-receipt.v1"
EXPECTED_CASE_COUNT = 10
EXPECTED_CLEAN_COUNT = 2
EXPECTED_DIRTY_COUNT = 8
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class ReceiptError(ValueError):
    """Raised when current-source evidence cannot be interpreted safely."""


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        raise ReceiptError(f"supporting_receipt_missing:{path.as_posix()}")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReceiptError(
            f"supporting_receipt_unreadable:{path.as_posix()}:{exc.__class__.__name__}"
        ) from exc
    if not isinstance(payload, dict):
        raise ReceiptError(f"supporting_receipt_not_object:{path.as_posix()}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _relative_evidence_path(repo_root: Path, value: Any, case_id: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ReceiptError(f"case_evidence_path_missing:{case_id}")
    declared = Path(value)
    if declared.is_absolute() or ".." in declared.parts:
        raise ReceiptError(f"case_evidence_path_invalid:{case_id}:{value}")
    resolved = (repo_root / declared).resolve()
    evidence_root = (repo_root / PRODUCTIZATION).resolve()
    try:
        resolved.relative_to(evidence_root)
    except ValueError as exc:
        raise ReceiptError(
            f"case_evidence_path_outside_productization:{case_id}"
        ) from exc
    if not resolved.exists() or not resolved.is_file():
        raise ReceiptError(f"case_evidence_file_missing:{case_id}:{value}")
    return declared


def _receipt_binding(
    repo_root: Path,
    path: Path,
    payload: dict[str, Any],
    source_commit_sha: str,
) -> dict[str, Any]:
    observed_source_sha = payload.get("source_commit_sha")
    return {
        "path": path.as_posix(),
        "sha256": _sha256(repo_root / path),
        "source_commit_sha": observed_source_sha,
        "source_commit_matches": observed_source_sha == source_commit_sha,
        "schema_version": payload.get("schema_version", ""),
    }


def _copy_support_files(
    *,
    repo_root: Path,
    support_dir: Path,
    paths: list[Path],
) -> None:
    resolved_support = (
        support_dir if support_dir.is_absolute() else repo_root / support_dir
    )
    resolved_support.mkdir(parents=True, exist_ok=True)
    expected_names = {path.name for path in paths}
    unexpected = sorted(
        path.name
        for path in resolved_support.iterdir()
        if path.name not in expected_names
        or not path.is_file()
        or path.suffix != ".json"
    )
    if unexpected:
        raise ReceiptError(f"support_bundle_unexpected_entries:{','.join(unexpected)}")
    for path in paths:
        source = path if path.is_absolute() else repo_root / path
        shutil.copyfile(source, resolved_support / path.name)


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key != "generated_at"
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def validate_receipt_schema(
    payload: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    schema_path: Path = DEFAULT_SCHEMA,
) -> None:
    schema = _load_json(repo_root, schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "$"
        raise ReceiptError(
            f"technical_receipt_schema_invalid:{location}:{first.message}"
        )


def build_current_source_receipt(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    acquisition_path: Path = DEFAULT_ACQUISITION,
    schema_path: Path = DEFAULT_SCHEMA,
) -> tuple[dict[str, Any], list[Path]]:
    repo_root = repo_root.resolve()
    if COMMIT_RE.fullmatch(source_commit_sha) is None:
        raise ReceiptError("source_commit_sha_invalid")
    manifest = _load_json(repo_root, manifest_path)
    acquisition = _load_json(repo_root, acquisition_path)
    support_payloads = {
        CLEAN_ACQUISITION: _load_json(repo_root, CLEAN_ACQUISITION),
        DIRTY_ACQUISITION: _load_json(repo_root, DIRTY_ACQUISITION),
        IMPORT_HEALTH: _load_json(repo_root, IMPORT_HEALTH),
        SOURCE_LICENSE: _load_json(repo_root, SOURCE_LICENSE),
        SILENT_IMPORT_LOSS: _load_json(repo_root, SILENT_IMPORT_LOSS),
    }
    support_bindings = {
        path.name: _receipt_binding(repo_root, path, payload, source_commit_sha)
        for path, payload in support_payloads.items()
    }
    technical_blockers: list[str] = []
    if manifest.get("schema_version") != "buildingsmart-ifc-current-source-manifest.v1":
        technical_blockers.append("manifest_schema_version_invalid")
    manifest_cases = manifest.get("cases")
    if not isinstance(manifest_cases, list):
        raise ReceiptError("manifest_cases_invalid")
    manifest_case_map = {
        str(row.get("case_id")): row
        for row in manifest_cases
        if isinstance(row, dict) and row.get("case_id")
    }
    if len(manifest_case_map) != EXPECTED_CASE_COUNT:
        technical_blockers.append("manifest_case_set_invalid")

    if acquisition.get("source_commit_sha") != source_commit_sha:
        technical_blockers.append("acquisition_source_commit_mismatch")
    if acquisition.get("manifest_sha256") != _sha256(repo_root / manifest_path):
        technical_blockers.append("acquisition_manifest_hash_mismatch")
    if acquisition.get("technical_contract_pass") is not True:
        technical_blockers.append("acquisition_technical_contract_not_passed")
    acquisition_artifacts = acquisition.get("artifacts")
    if not isinstance(acquisition_artifacts, list):
        raise ReceiptError("acquisition_artifacts_invalid")
    acquired_cases = {
        str(row.get("case_id")): row
        for row in acquisition_artifacts
        if isinstance(row, dict) and row.get("artifact_kind") == "case"
    }
    acquired_licenses = [
        row
        for row in acquisition_artifacts
        if isinstance(row, dict) and row.get("artifact_kind") == "license"
    ]
    if set(acquired_cases) != set(manifest_case_map):
        technical_blockers.append("acquisition_case_set_mismatch")
    if len(acquired_licenses) != 2 or not all(
        row.get("verified") is True for row in acquired_licenses
    ):
        technical_blockers.append("upstream_license_material_not_exact")

    import_health = support_payloads[IMPORT_HEALTH]
    import_cases_raw = import_health.get("case_receipts")
    if not isinstance(import_cases_raw, list):
        raise ReceiptError("import_health_case_receipts_invalid")
    import_case_map = {
        str(row.get("case_id")): row
        for row in import_cases_raw
        if isinstance(row, dict) and row.get("case_id")
    }
    if set(import_case_map) != set(manifest_case_map):
        technical_blockers.append("import_health_case_set_mismatch")

    case_receipts: list[dict[str, Any]] = []
    support_files: list[Path] = [
        acquisition_path,
        *support_payloads.keys(),
    ]
    for case_id in sorted(manifest_case_map):
        manifest_row = manifest_case_map[case_id]
        acquired_row = acquired_cases.get(case_id, {})
        import_row = import_case_map.get(case_id, {})
        case_blockers: list[str] = []
        if acquired_row.get("verified") is not True:
            case_blockers.append("source_bytes_not_verified")
        if acquired_row.get("expected_sha256") != manifest_row.get("sha256"):
            case_blockers.append("acquisition_expected_hash_manifest_mismatch")
        if acquired_row.get("observed_sha256") != manifest_row.get("sha256"):
            case_blockers.append("acquisition_observed_hash_manifest_mismatch")
        if import_row.get("source_sha256") != manifest_row.get("sha256"):
            case_blockers.append("import_source_hash_manifest_mismatch")
        if import_row.get("lane_kind") != manifest_row.get("lane_kind"):
            case_blockers.append("import_lane_kind_manifest_mismatch")
        if import_row.get("source_file_acquired") is not True:
            case_blockers.append("import_source_not_acquired")
        if import_row.get("import_health_executed") is not True:
            case_blockers.append("import_health_not_executed")
        if import_row.get("import_health_contract_pass") is not True:
            case_blockers.append("import_health_contract_not_passed")
        silent_gate = import_row.get("silent_import_loss_gate")
        if (
            not isinstance(silent_gate, dict)
            or silent_gate.get("contract_pass") is not True
        ):
            case_blockers.append("case_silent_import_loss_gate_not_passed")
        elif silent_gate.get("visible_entity_accounting") is not True:
            case_blockers.append("case_visible_entity_accounting_missing")
        execution = import_row.get("execution")
        if not isinstance(execution, dict):
            case_blockers.append("case_execution_receipt_missing")
            result_path = None
            report_path = None
        else:
            result_path = _relative_evidence_path(
                repo_root,
                execution.get("result_path"),
                case_id,
            )
            report_path = _relative_evidence_path(
                repo_root,
                execution.get("report_path"),
                case_id,
            )
            support_files.extend([result_path, report_path])
        if case_blockers:
            technical_blockers.extend(f"{case_id}:{item}" for item in case_blockers)
        case_receipts.append(
            {
                "case_id": case_id,
                "lane_kind": manifest_row.get("lane_kind"),
                "upstream_repository": manifest_row.get("upstream_repository"),
                "upstream_commit_sha": manifest_row.get("upstream_commit_sha"),
                "upstream_path": manifest_row.get("upstream_path"),
                "source_sha256": manifest_row.get("sha256"),
                "source_byte_length": manifest_row.get("byte_length"),
                "license_id": manifest_row.get("license_id"),
                "import_health_executed": import_row.get("import_health_executed")
                is True,
                "import_health_contract_pass": import_row.get(
                    "import_health_contract_pass"
                )
                is True,
                "silent_import_loss_gate_pass": isinstance(silent_gate, dict)
                and silent_gate.get("contract_pass") is True,
                "visible_entity_accounting": isinstance(silent_gate, dict)
                and silent_gate.get("visible_entity_accounting") is True,
                "record_count": silent_gate.get("record_count")
                if isinstance(silent_gate, dict)
                else None,
                "parsed_record_count": silent_gate.get("parsed_record_count")
                if isinstance(silent_gate, dict)
                else None,
                "result_path": result_path.as_posix() if result_path else "",
                "result_sha256": _sha256(repo_root / result_path)
                if result_path
                else "",
                "report_path": report_path.as_posix() if report_path else "",
                "report_sha256": _sha256(repo_root / report_path)
                if report_path
                else "",
                "technical_contract_pass": not case_blockers,
                "blockers": case_blockers,
            }
        )

    for name, binding in support_bindings.items():
        if binding["source_commit_matches"] is not True:
            technical_blockers.append(
                f"supporting_receipt_source_commit_mismatch:{name}"
            )
    silent_status = support_payloads[SILENT_IMPORT_LOSS]
    if silent_status.get("technical_silent_import_loss_zero") is not True:
        technical_blockers.append("phase6_technical_silent_import_loss_zero_not_proven")
    if silent_status.get("technical_direct_blockers") not in ([], None):
        technical_blockers.append("phase6_technical_direct_blockers_present")
    expected_counts = {
        "source_file_acquired_count": EXPECTED_CASE_COUNT,
        "source_checksum_attached_count": EXPECTED_CASE_COUNT,
        "import_health_execution_count": EXPECTED_CASE_COUNT,
        "import_health_contract_pass_count": EXPECTED_CASE_COUNT,
        "visible_entity_accounting_case_count": EXPECTED_CASE_COUNT,
        "silent_import_loss_gate_pass_count": EXPECTED_CASE_COUNT,
    }
    for key, expected in expected_counts.items():
        if import_health.get(key) != expected:
            technical_blockers.append(f"import_health_count_invalid:{key}")
    lane_counts = {
        "clean": sum(row["lane_kind"] == "clean" for row in case_receipts),
        "dirty": sum(row["lane_kind"] == "dirty" for row in case_receipts),
    }
    if lane_counts != {"clean": EXPECTED_CLEAN_COUNT, "dirty": EXPECTED_DIRTY_COUNT}:
        technical_blockers.append("import_health_lane_counts_invalid")
    technical_blockers = sorted(set(technical_blockers))
    technical_contract_pass = not technical_blockers

    source_license = support_payloads[SOURCE_LICENSE]
    nontechnical_blockers = sorted(
        {
            str(blocker)
            for blocker in [
                *source_license.get("blockers", []),
                *silent_status.get("product_release_credit_blockers", []),
                "current_source_technical_workflow_not_product_legal_authority",
            ]
            if str(blocker)
        }
    )
    legal_and_product_blockers = [
        blocker
        for blocker in nontechnical_blockers
        if any(
            token in blocker
            for token in (
                "license",
                "legal",
                "quantity_credit",
                "product_legal_authority",
            )
        )
    ]
    payload = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha,
        "status": "technical_ready_product_authority_blocked"
        if technical_contract_pass
        else "technical_blocked",
        "technical_contract_pass": technical_contract_pass,
        "receipt_schema": {
            "path": schema_path.as_posix(),
            "sha256": _sha256(repo_root / schema_path),
        },
        "manifest": {
            "path": manifest_path.as_posix(),
            "sha256": _sha256(repo_root / manifest_path),
            "schema_version": manifest.get("schema_version"),
            "case_count": len(manifest_case_map),
            "storage_boundary": manifest.get("storage_boundary"),
        },
        "counts": {
            "required_case_count": EXPECTED_CASE_COUNT,
            "case_count": len(case_receipts),
            "clean_case_count": lane_counts["clean"],
            "dirty_case_count": lane_counts["dirty"],
            "source_file_acquired_count": import_health.get(
                "source_file_acquired_count", 0
            ),
            "source_checksum_attached_count": import_health.get(
                "source_checksum_attached_count", 0
            ),
            "import_health_execution_count": import_health.get(
                "import_health_execution_count", 0
            ),
            "import_health_contract_pass_count": import_health.get(
                "import_health_contract_pass_count", 0
            ),
            "visible_entity_accounting_case_count": import_health.get(
                "visible_entity_accounting_case_count", 0
            ),
            "silent_import_loss_gate_pass_count": import_health.get(
                "silent_import_loss_gate_pass_count", 0
            ),
        },
        "claims": {
            "same_operator_current_source_execution": technical_contract_pass,
            "immutable_source_and_license_byte_identity": technical_contract_pass,
            "technical_silent_import_loss_zero": technical_contract_pass,
            "text_scan_import_health_only": True,
            "solver_ready_geometry_or_topology": False,
            "independent_reproduction": False,
            "product_legal_approval": False,
            "redistribution_authority": False,
            "commercial_use_authority": False,
            "phase3_quantity_credit": False,
            "release_authority": False,
        },
        "case_receipts": case_receipts,
        "supporting_receipts": support_bindings,
        "technical_blockers": technical_blockers,
        "legal_and_product_blockers": legal_and_product_blockers,
        "nontechnical_blockers": nontechnical_blockers,
        "spillover_blockers": silent_status.get("spillover_blockers", []),
        "raw_ifc_files_uploaded": False,
        "claim_boundary": (
            "This source-bound artifact proves exact-byte acquisition and same-operator "
            "model-health execution for ten clean/dirty IFC files, including visible entity "
            "accounting and the scoped technical silent-import-loss-zero gate. The adapter is "
            "still a STEP text scan. Raw IFC files remain in ignored private_corpus storage. "
            "The artifact does not prove canonical geometry/topology, independent reproduction, "
            "product/legal approval, redistribution or commercial-use permission, Phase 3 "
            "quantity credit, or release authority."
        ),
    }
    return payload, list(dict.fromkeys(support_files))


def write_current_source_receipt(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    acquisition_path: Path = DEFAULT_ACQUISITION,
    schema_path: Path = DEFAULT_SCHEMA,
    out_path: Path = DEFAULT_OUTPUT,
    support_dir: Path = DEFAULT_SUPPORT_DIR,
    copy_support: bool = True,
) -> dict[str, Any]:
    payload, support_files = build_current_source_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
        manifest_path=manifest_path,
        acquisition_path=acquisition_path,
        schema_path=schema_path,
    )
    validate_receipt_schema(payload, repo_root=repo_root, schema_path=schema_path)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    if copy_support:
        _copy_support_files(
            repo_root=repo_root,
            support_dir=support_dir,
            paths=support_files,
        )
    return payload


def check_current_source_receipt(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    acquisition_path: Path = DEFAULT_ACQUISITION,
    schema_path: Path = DEFAULT_SCHEMA,
    out_path: Path = DEFAULT_OUTPUT,
) -> tuple[bool, str]:
    expected, _ = build_current_source_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
        manifest_path=manifest_path,
        acquisition_path=acquisition_path,
        schema_path=schema_path,
    )
    validate_receipt_schema(expected, repo_root=repo_root, schema_path=schema_path)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"current_source_receipt_missing:{out_path.as_posix()}"
    existing = _load_json(repo_root, out_path)
    validate_receipt_schema(existing, repo_root=repo_root, schema_path=schema_path)
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "current_source_receipt_mismatch"
    if expected["technical_contract_pass"] is not True:
        return False, "current_source_technical_contract_blocked"
    return True, "current_source_receipt_consistent_and_technical_ready"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit-sha", required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--acquisition", type=Path, default=DEFAULT_ACQUISITION)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--support-dir", type=Path, default=DEFAULT_SUPPORT_DIR)
    parser.add_argument("--no-copy-support", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--fail-technical-blocked", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.check:
            ok, message = check_current_source_receipt(
                source_commit_sha=args.source_commit_sha,
                manifest_path=args.manifest,
                acquisition_path=args.acquisition,
                schema_path=args.schema,
                out_path=args.out,
            )
            print(f"IFC current-source receipt check: {message}")
            return 0 if ok else 1
        payload = write_current_source_receipt(
            source_commit_sha=args.source_commit_sha,
            manifest_path=args.manifest,
            acquisition_path=args.acquisition,
            schema_path=args.schema,
            out_path=args.out,
            support_dir=args.support_dir,
            copy_support=not args.no_copy_support,
        )
    except (ReceiptError, json.JSONDecodeError) as exc:
        print(f"IFC current-source receipt: technical_blocked | {exc}")
        return 1
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "IFC current-source receipt: "
            f"{payload['status']} | technical="
            f"{payload['counts']['import_health_contract_pass_count']}/"
            f"{payload['counts']['required_case_count']} | product_authority=false"
        )
    if args.fail_technical_blocked and payload["technical_contract_pass"] is not True:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
