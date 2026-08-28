#!/usr/bin/env python3
"""Execute and validate the bounded current-source MGT import-health corpus."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path("benchmarks/import_health/mgt_current_source.v1.json")
DEFAULT_MANIFEST_SCHEMA = Path(
    "canonical/mgt-import-health-current-source-manifest.v1.schema.json"
)
DEFAULT_RECEIPT_SCHEMA = Path(
    "canonical/mgt-import-health-current-source-technical-receipt.v1.schema.json"
)
DEFAULT_EVIDENCE_DIR = Path(".ci/mgt-import-health-current-source")
DEFAULT_OUTPUT = DEFAULT_EVIDENCE_DIR / "technical-receipt.json"
PARSER = Path("implementation/phase1/parse_midas_mgt_to_json_npz.py")
MANIFEST_VERSION = "mgt-import-health-current-source-manifest.v1"
RECEIPT_VERSION = "mgt-import-health-current-source-technical-receipt.v1"
TARGET_CASE_COUNT = 10
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
FALSE_AUTHORITY_CLAIMS = (
    "solver_ready_import",
    "design_authority",
    "independent_reproduction",
    "product_legal_approval",
    "redistribution_authority",
    "commercial_use_authority",
    "release_authority",
)


class ReceiptError(ValueError):
    """Raised when a source-bound receipt cannot be built safely."""


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    try:
        def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ReceiptError(
                        f"json_duplicate_key:{path.as_posix()}:{key}"
                    )
                result[key] = value
            return result

        payload = json.loads(
            resolved.read_text(encoding="utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ReceiptError(f"json_nonfinite_number:{path.as_posix()}:{token}")
            ),
        )

        def require_finite(value: Any, location: str = "$") -> None:
            if isinstance(value, float) and not math.isfinite(value):
                raise ReceiptError(
                    f"json_nonfinite_number:{path.as_posix()}:{location}"
                )
            if isinstance(value, dict):
                for key, nested in value.items():
                    require_finite(nested, f"{location}.{key}")
            elif isinstance(value, list):
                for index, nested in enumerate(value):
                    require_finite(nested, f"{location}[{index}]")

        require_finite(payload)
    except ReceiptError:
        raise
    except Exception as exc:
        raise ReceiptError(
            f"json_unreadable:{path.as_posix()}:{exc.__class__.__name__}"
        ) from exc
    if not isinstance(payload, dict):
        raise ReceiptError(f"json_not_object:{path.as_posix()}")
    return payload


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_errors(payload: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
    return [
        f"{'.'.join(str(part) for part in error.path) or '$'}:{error.message}"
        for error in errors
    ]


def _validate_schema(
    payload: dict[str, Any], *, repo_root: Path, schema_path: Path, label: str
) -> None:
    errors = _schema_errors(payload, _load_json(repo_root, schema_path))
    if errors:
        raise ReceiptError(f"{label}_schema_invalid:{errors[0]}")


def _git_output(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _git_tracked(repo_root: Path, path: str) -> bool:
    completed = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", path],
        cwd=repo_root,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


def _clean_record(raw: str) -> str:
    stripped = raw.lstrip()
    if not stripped or stripped.startswith("#") or stripped.startswith("$"):
        return ""
    if ";" in raw:
        raw = raw.split(";", 1)[0]
    return raw.strip()


def _canonical_model_token(token: str) -> str:
    value = token.strip()
    try:
        number = float(value)
    except ValueError:
        return value.upper()
    if number.is_integer():
        return str(int(number))
    return format(number, ".17g")


def _model_identity_sha256(section_rows: dict[str, list[str]]) -> str:
    node_rows = [
        [_canonical_model_token(token) for token in row.split(",")]
        for row in section_rows.get("NODE", [])
    ]
    element_rows: list[list[str]] = []
    for row in section_rows.get("ELEMENT", []):
        tokens = [token.strip() for token in row.split(",")]
        if len(tokens) >= 6:
            identity_tokens = [tokens[0], tokens[1], *tokens[4:]]
        else:
            identity_tokens = tokens
        element_rows.append(
            [_canonical_model_token(token) for token in identity_tokens]
        )
    node_rows.sort()
    element_rows.sort()
    return _sha256_bytes(
        _json_text({"nodes": node_rows, "elements": element_rows}).encode("utf-8")
    )


def _scan_source(path: Path) -> dict[str, Any]:
    raw_bytes = path.read_bytes()
    text = raw_bytes.decode("utf-8", errors="replace")
    section = "ROOT"
    section_rows: dict[str, list[str]] = defaultdict(list)
    ordered_records: list[tuple[str, str]] = []
    data_line_indexes: list[int] = []
    section_line_indexes: dict[str, list[int]] = defaultdict(list)
    raw_lines = text.splitlines(keepends=True)
    raw_byte_lines = raw_bytes.splitlines(keepends=True)
    for index, raw_with_ending in enumerate(raw_lines):
        cleaned = _clean_record(raw_with_ending.rstrip("\r\n"))
        if not cleaned:
            continue
        if cleaned.startswith("*"):
            header = cleaned[1:].strip()
            section = header.split(",", 1)[0].strip().upper() or "ROOT"
            continue
        section_rows[section].append(cleaned)
        ordered_records.append((section, cleaned))
        data_line_indexes.append(index)
        section_line_indexes[section].append(index)
    fingerprint = _sha256_bytes(
        _json_text([[section, row] for section, row in ordered_records]).encode(
            "utf-8"
        )
    )
    return {
        "raw_bytes": raw_bytes,
        "raw_lines": raw_lines,
        "raw_byte_lines": raw_byte_lines,
        "data_line_indexes": data_line_indexes,
        "section_line_indexes": dict(section_line_indexes),
        "section_rows": dict(section_rows),
        "section_row_counts": {
            key: len(value) for key, value in sorted(section_rows.items())
        },
        "data_row_count": len(ordered_records),
        "record_fingerprint_sha256": fingerprint,
        "model_identity_sha256": _model_identity_sha256(dict(section_rows)),
        "utf8_replacement_character_count": text.count("\ufffd"),
    }


def _leading_integer_ids(rows: list[str]) -> list[int]:
    values: list[int] = []
    for row in rows:
        token = row.split(",", 1)[0].strip()
        try:
            value = float(token)
        except ValueError:
            continue
        if value.is_integer():
            values.append(int(value))
    return values


def _recognized_section_counts(
    scan: dict[str, Any], report: dict[str, Any]
) -> dict[str, int]:
    section_counts = scan["section_row_counts"]
    diagnostics = report.get("parser_diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    row_parse = diagnostics.get("row_parse")
    row_parse = row_parse if isinstance(row_parse, dict) else {}
    typed = diagnostics.get("typed_section_row_count")
    typed = typed if isinstance(typed, dict) else {}
    recognized: Counter[str] = Counter()
    recognized["NODE"] = int(row_parse.get("node_rows_parsed", 0) or 0)
    recognized["ELEMENT"] = int(row_parse.get("element_rows_parsed", 0) or 0)
    recognized["MATERIAL"] = int(row_parse.get("material_rows_parsed", 0) or 0)
    recognized["SECTION"] = int(row_parse.get("section_rows_parsed", 0) or 0)
    for key, value in typed.items():
        if key not in {"NODE", "ELEMENT", "MATERIAL", "SECTION"}:
            recognized[str(key)] += int(value or 0)
    if int(section_counts.get("UNIT", 0)) > 0:
        recognized["UNIT"] = 1
    recognized["CONSTRAINT"] = int(row_parse.get("constraint_rows", 0) or 0)
    coarsening = report.get("coarsening")
    coarsening = coarsening if isinstance(coarsening, dict) else {}
    recognized["ELASTICLINK"] = int(
        coarsening.get("elastic_link_count", 0) or 0
    )
    return {
        key: min(int(section_counts.get(key, 0)), max(0, int(value)))
        for key, value in sorted(recognized.items())
        if int(value) > 0
    }


def _entity_accounting(
    scan: dict[str, Any], report: dict[str, Any], model: dict[str, Any] | None
) -> dict[str, Any]:
    diagnostics = report.get("parser_diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    row_parse = diagnostics.get("row_parse")
    row_parse = row_parse if isinstance(row_parse, dict) else {}
    model_body = model.get("model") if isinstance(model, dict) else {}
    model_body = model_body if isinstance(model_body, dict) else {}
    output_nodes = model_body.get("nodes")
    output_nodes = output_nodes if isinstance(output_nodes, list) else []
    output_elements = model_body.get("elements")
    output_elements = output_elements if isinstance(output_elements, list) else []
    # Parser output is canonicalized by entity ID.  Source rows are allowed to
    # be authored in any order, so compare normalized ID sets rather than the
    # incidental order of records in the MGT file.
    source_nodes = sorted(
        _leading_integer_ids(scan["section_rows"].get("NODE", []))
    )
    source_elements = sorted(
        _leading_integer_ids(scan["section_rows"].get("ELEMENT", []))
    )
    output_node_ids = sorted(
        int(row["id"])
        for row in output_nodes
        if isinstance(row, dict) and isinstance(row.get("id"), (int, float))
    )
    output_element_ids = sorted(
        int(row["id"])
        for row in output_elements
        if isinstance(row, dict) and isinstance(row.get("id"), (int, float))
    )
    parser_contract_pass = report.get("contract_pass") is True
    return {
        "node": {
            "source_row_count": len(scan["section_rows"].get("NODE", [])),
            "source_id_count": len(source_nodes),
            "parser_reported_row_count": int(row_parse.get("node_rows", 0) or 0),
            "parser_reported_parsed_count": int(
                row_parse.get("node_rows_parsed", 0) or 0
            ),
            "parser_reported_skipped_count": int(
                row_parse.get("node_rows_skipped", 0) or 0
            ),
            "output_count": len(output_node_ids),
            "source_id_sha256": _sha256_bytes(
                _json_text(source_nodes).encode("utf-8")
            ),
            "output_id_sha256": _sha256_bytes(
                _json_text(output_node_ids).encode("utf-8")
            ),
        },
        "element": {
            "source_row_count": len(
                scan["section_rows"].get("ELEMENT", [])
            ),
            "source_id_count": len(source_elements),
            "parser_reported_row_count": int(
                row_parse.get("element_rows", 0) or 0
            ),
            "parser_reported_parsed_count": int(
                row_parse.get("element_rows_parsed", 0) or 0
            ),
            "parser_reported_skipped_count": int(
                row_parse.get("element_rows_skipped", 0) or 0
            ),
            "output_count": len(output_element_ids),
            "source_id_sha256": _sha256_bytes(
                _json_text(source_elements).encode("utf-8")
            ),
            "output_id_sha256": _sha256_bytes(
                _json_text(output_element_ids).encode("utf-8")
            ),
        },
        "material": {
            "source_row_count": len(
                scan["section_rows"].get("MATERIAL", [])
            ),
            "parser_reported_row_count": int(
                row_parse.get("material_rows", 0) or 0
            ),
            "parser_reported_parsed_count": int(
                row_parse.get("material_rows_parsed", 0) or 0
            ),
        },
        "section": {
            "source_row_count": len(
                scan["section_rows"].get("SECTION", [])
            ),
            "parser_reported_row_count": int(
                row_parse.get("section_rows", 0) or 0
            ),
            "parser_reported_parsed_count": int(
                row_parse.get("section_rows_parsed", 0) or 0
            ),
        },
        "output_suppressed_by_parser_contract": bool(
            not parser_contract_pass and model is None
        ),
    }


def _accounting_errors(case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    record = case["record_accounting"]
    if (
        int(record["parser_recognized_row_count"])
        + int(record["visible_unsupported_or_omitted_row_count"])
        != int(record["source_data_row_count"])
    ):
        errors.append("record_accounting_total_mismatch")
    if int(record["unaccounted_row_count"]) != 0:
        errors.append("unaccounted_rows_nonzero")
    entity = case["entity_accounting"]
    for family in ("node", "element"):
        row = entity[family]
        if int(row["source_row_count"]) != int(row["parser_reported_row_count"]):
            errors.append(f"{family}_source_report_count_mismatch")
        if int(row["parser_reported_parsed_count"]) + int(
            row["parser_reported_skipped_count"]
        ) != int(row["parser_reported_row_count"]):
            errors.append(f"{family}_parser_balance_mismatch")
        if case["parser"]["contract_pass"] is True and int(
            row["output_count"]
        ) != int(row["parser_reported_parsed_count"]):
            errors.append(f"{family}_output_count_mismatch")
        if (
            case["parser"]["contract_pass"] is True
            and int(row["parser_reported_skipped_count"]) == 0
            and row["source_id_sha256"] != row["output_id_sha256"]
        ):
            errors.append(f"{family}_output_identity_mismatch")
    for family in ("material", "section"):
        row = entity[family]
        if int(row["source_row_count"]) != int(row["parser_reported_row_count"]):
            errors.append(f"{family}_source_report_count_mismatch")
        if int(row["parser_reported_parsed_count"]) > int(
            row["parser_reported_row_count"]
        ):
            errors.append(f"{family}_parsed_count_exceeds_source")
    return errors


def _case_contract_errors(case: dict[str, Any]) -> list[str]:
    errors = _accounting_errors(case)
    source = case["source"]
    parser = case["parser"]
    negative = case["negative_silent_loss_gate"]
    rights = case["provenance_and_rights"]
    visible_count = int(
        case["record_accounting"]["visible_unsupported_or_omitted_row_count"]
    )
    if source["tracked"] is not True:
        errors.append("source_not_tracked")
    if source["expected_sha256"] != source["observed_sha256"]:
        errors.append("source_sha256_mismatch")
    if source["expected_size_bytes"] != source["observed_size_bytes"]:
        errors.append("source_size_mismatch")
    return_code_expected = (
        parser["contract_pass"] is True and parser["return_code"] == 0
    ) or (parser["contract_pass"] is False and parser["return_code"] != 0)
    if parser["return_code_matches_contract"] is not return_code_expected:
        errors.append("parser_return_code_contract_mismatch")
    if not return_code_expected:
        errors.append("parser_return_code_contract_invalid")
    observed_expected = _observed_outcome(
        parser_contract_pass=parser["contract_pass"],
        visible_omitted_count=visible_count,
    )
    if case["observed_parser_outcome"] != observed_expected:
        errors.append("observed_parser_outcome_mismatch")
    if case["expected_parser_outcome"] != case["observed_parser_outcome"]:
        errors.append("expected_parser_outcome_mismatch")
    if case["corpus_class"] == "clean" and (
        visible_count != 0
        or int(source["utf8_replacement_character_count"]) != 0
    ):
        errors.append("clean_case_has_visible_loss_risk")
    if case["corpus_class"] == "dirty" and (
        visible_count == 0
        and int(source["utf8_replacement_character_count"]) == 0
    ):
        errors.append("dirty_case_has_no_visible_loss_risk")
    if negative["source_record_deletion_detected"] is not True:
        errors.append("source_record_deletion_not_detected")
    if negative["accounting_record_deletion_detected"] is not True:
        errors.append("accounting_record_deletion_not_detected")
    if negative.get("parser_replay_executed") is not True:
        errors.append("negative_parser_replay_not_executed")
    if negative.get("parser_return_code_matches_contract") is not True:
        errors.append("negative_parser_return_code_contract_mismatch")
    if negative.get("raw_mutated_input_retained") is not False:
        errors.append("negative_raw_input_retention_invalid")
    if rights["redistribution_reviewed"] is not False:
        errors.append("redistribution_review_unexpectedly_true")
    if rights["commercial_use_reviewed"] is not False:
        errors.append("commercial_use_review_unexpectedly_true")
    return sorted(set(errors))


def _delete_first_node_record(scan: dict[str, Any]) -> bytes:
    indexes = scan["section_line_indexes"].get("NODE", [])
    if not indexes:
        raise ReceiptError("negative_mutation_node_record_missing")
    lines = list(scan["raw_byte_lines"])
    del lines[indexes[0]]
    return b"".join(lines)


def _stable_report_sha256(report: dict[str, Any]) -> str:
    def project(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: project(item)
                for key, item in value.items()
                if key != "generated_at"
            }
        if isinstance(value, list):
            return [project(item) for item in value]
        return value

    return _sha256_bytes(_json_text(project(report)).encode("utf-8"))


def _observed_outcome(
    *, parser_contract_pass: bool, visible_omitted_count: int
) -> str:
    if not parser_contract_pass:
        return "reject_with_visible_omissions"
    if visible_omitted_count > 0:
        return "pass_with_visible_unsupported_rows"
    return "pass"


def _run_parser(
    *,
    repo_root: Path,
    source_path: str,
    case_id: str,
    evidence_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any] | None, int, Path]:
    support_dir = evidence_dir / "case-reports"
    work_dir = evidence_dir / "work" / case_id
    support_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    report_path = support_dir / f"{case_id}.parser-report.json"
    model_path = work_dir / "model.json"
    npz_path = work_dir / "graph.npz"
    edge_path = work_dir / "edges.json"
    command = [
        sys.executable,
        PARSER.as_posix(),
        "--mgt",
        source_path,
        "--json-out",
        model_path.as_posix(),
        "--npz-out",
        npz_path.as_posix(),
        "--report-out",
        report_path.as_posix(),
        "--edge-list-out",
        edge_path.as_posix(),
        "--no-forbid-synthetic-source",
        "--min-nodes",
        "2",
        "--min-elements",
        "1",
        "--no-resolve-rigid-links",
        "--no-drop-unreferenced-nodes",
        "--max-element-skip-count",
        "1000000",
        "--max-element-skip-ratio",
        "1.0",
    ]
    completed = subprocess.run(
        command,
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    report = _load_json(repo_root, report_path)
    model = _load_json(repo_root, model_path) if model_path.exists() else None
    shutil.rmtree(work_dir)
    return report, model, completed.returncode, report_path


def _negative_silent_loss_gate(
    *,
    repo_root: Path,
    case_id: str,
    original_scan: dict[str, Any],
    original_entity: dict[str, Any],
    original_sha256: str,
    evidence_dir: Path,
) -> dict[str, Any]:
    mutated_bytes = _delete_first_node_record(original_scan)
    negative_source = (
        evidence_dir / "negative-inputs" / f"{case_id}.deleted-node.mgt"
    )
    negative_source_abs = _resolve(repo_root, negative_source)
    negative_source_abs.parent.mkdir(parents=True, exist_ok=True)
    negative_source_abs.write_bytes(mutated_bytes)
    mutated_scan = _scan_source(negative_source_abs)
    negative_case_id = f"{case_id}.deleted-node"
    try:
        report, model, returncode, report_path = _run_parser(
            repo_root=repo_root,
            source_path=negative_source.as_posix(),
            case_id=negative_case_id,
            evidence_dir=evidence_dir,
        )
    finally:
        negative_source_abs.unlink(missing_ok=True)
        try:
            negative_source_abs.parent.rmdir()
        except OSError:
            pass

    report_contract_pass = report.get("contract_pass") is True
    return_code_matches = bool(
        (report_contract_pass and returncode == 0)
        or (not report_contract_pass and returncode != 0)
    )
    mutated_entity = _entity_accounting(mutated_scan, report, model)
    original_node = original_entity["node"]
    mutated_node = mutated_entity["node"]
    report_source = report.get("source_provenance")
    report_source = report_source if isinstance(report_source, dict) else {}
    mutated_sha256 = _sha256_bytes(mutated_bytes)
    parser_source_bound = bool(
        report_source.get("path") == negative_source.as_posix()
        and report_source.get("sha256") == mutated_sha256
        and report_source.get("size_bytes") == len(mutated_bytes)
    )
    node_balance = bool(
        mutated_node["source_row_count"]
        == int(original_node["source_row_count"]) - 1
        and mutated_node["parser_reported_row_count"]
        == mutated_node["source_row_count"]
        and int(mutated_node["parser_reported_parsed_count"])
        + int(mutated_node["parser_reported_skipped_count"])
        == int(mutated_node["parser_reported_row_count"])
    )
    parser_observed_deletion = bool(
        (
            report_contract_pass
            and mutated_node["output_count"]
            == mutated_node["parser_reported_parsed_count"]
            and mutated_node["source_id_sha256"]
            != original_node["source_id_sha256"]
            and (
                int(mutated_node["parser_reported_skipped_count"]) > 0
                or mutated_node["output_id_sha256"]
                == mutated_node["source_id_sha256"]
            )
        )
        or (
            not report_contract_pass
            and model is None
            and str(report.get("reason_code", "")) not in {"", "PASS"}
        )
    )
    source_deletion_detected = bool(
        mutated_sha256 != original_sha256
        and int(mutated_scan["data_row_count"])
        == int(original_scan["data_row_count"]) - 1
    )
    return {
        "source_record_deletion_detected": source_deletion_detected,
        "accounting_record_deletion_detected": bool(
            source_deletion_detected
            and return_code_matches
            and parser_source_bound
            and node_balance
            and parser_observed_deletion
        ),
        "parser_replay_executed": True,
        "parser_return_code": returncode,
        "parser_contract_pass": report_contract_pass,
        "parser_return_code_matches_contract": return_code_matches,
        "deleted_record_kind": "node",
        "mutated_source_sha256": mutated_sha256,
        "mutated_source_data_row_count": int(mutated_scan["data_row_count"]),
        "mutated_node_id_sha256": mutated_node["source_id_sha256"],
        "parser_report_path": report_path.as_posix(),
        "parser_report_semantic_sha256": _stable_report_sha256(report),
        "raw_mutated_input_retained": False,
        "source_mutation_reason": "source_sha256_and_record_count_mismatch",
        "accounting_mutation_reason": (
            "live_parser_replay_detected_deleted_node_identity"
        ),
    }


def _case_receipt(
    *,
    repo_root: Path,
    manifest_case: dict[str, Any],
    evidence_dir: Path,
) -> dict[str, Any]:
    source_rel = str(manifest_case["path"])
    source_declared = Path(source_rel)
    if source_declared.is_absolute() or ".." in source_declared.parts:
        raise ReceiptError(f"case_source_path_invalid:{manifest_case['case_id']}")
    source = _resolve(repo_root, source_declared).resolve()
    try:
        source.relative_to(repo_root)
    except ValueError as exc:
        raise ReceiptError(
            f"case_source_path_outside_repo:{manifest_case['case_id']}"
        ) from exc
    observed_sha = _sha256(source)
    observed_size = source.stat().st_size
    scan = _scan_source(source)
    report, model, returncode, report_path = _run_parser(
        repo_root=repo_root,
        source_path=source_rel,
        case_id=str(manifest_case["case_id"]),
        evidence_dir=evidence_dir,
    )
    recognized = _recognized_section_counts(scan, report)
    visible_by_section = {
        key: int(count) - int(recognized.get(key, 0))
        for key, count in scan["section_row_counts"].items()
        if int(count) - int(recognized.get(key, 0)) > 0
    }
    recognized_total = sum(recognized.values())
    visible_total = sum(visible_by_section.values())
    entity = _entity_accounting(scan, report, model)
    observed = _observed_outcome(
        parser_contract_pass=report.get("contract_pass") is True,
        visible_omitted_count=visible_total,
    )
    parser_return_expected = (report.get("contract_pass") is True and returncode == 0) or (
        report.get("contract_pass") is not True and returncode != 0
    )
    case = {
        "case_id": manifest_case["case_id"],
        "lineage_id": manifest_case["lineage_id"],
        "path": source_rel,
        "corpus_class": manifest_case["corpus_class"],
        "expected_parser_outcome": manifest_case["expected_parser_outcome"],
        "observed_parser_outcome": observed,
        "source": {
            "tracked": _git_tracked(repo_root, source_rel),
            "expected_sha256": manifest_case["expected_sha256"],
            "observed_sha256": observed_sha,
            "expected_size_bytes": manifest_case["expected_size_bytes"],
            "observed_size_bytes": observed_size,
            "record_fingerprint_sha256": scan["record_fingerprint_sha256"],
            "model_identity_sha256": scan["model_identity_sha256"],
            "utf8_replacement_character_count": scan[
                "utf8_replacement_character_count"
            ],
        },
        "provenance_and_rights": {
            key: manifest_case[key]
            for key in (
                "source_kind",
                "source_owner",
                "origin_url",
                "provenance_status",
                "rights_status",
                "redistribution_reviewed",
                "commercial_use_reviewed",
            )
        },
        "parser": {
            "script": PARSER.as_posix(),
            "return_code": returncode,
            "return_code_matches_contract": parser_return_expected,
            "contract_pass": report.get("contract_pass") is True,
            "reason_code": str(report.get("reason_code", "")),
            "report_path": report_path.as_posix(),
            "report_sha256": _sha256(_resolve(repo_root, report_path)),
        },
        "record_accounting": {
            "source_data_row_count": scan["data_row_count"],
            "parser_recognized_row_count": recognized_total,
            "visible_unsupported_or_omitted_row_count": visible_total,
            "visible_unsupported_or_omitted_by_section": visible_by_section,
            "unaccounted_row_count": int(
                scan["data_row_count"] - recognized_total - visible_total
            ),
        },
        "entity_accounting": entity,
        "negative_silent_loss_gate": {},
        "contract_pass": False,
    }
    case["negative_silent_loss_gate"] = _negative_silent_loss_gate(
        repo_root=repo_root,
        case_id=str(manifest_case["case_id"]),
        original_scan=scan,
        original_entity=entity,
        original_sha256=observed_sha,
        evidence_dir=evidence_dir,
    )
    case["contract_pass"] = not _case_contract_errors(case)
    return case


def validate_receipt_semantics(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    cases = payload.get("cases")
    cases = cases if isinstance(cases, list) else []
    summary = payload.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    case_ids = [str(row.get("case_id", "")) for row in cases if isinstance(row, dict)]
    lineages = [str(row.get("lineage_id", "")) for row in cases if isinstance(row, dict)]
    source_hashes = [
        str((row.get("source") or {}).get("observed_sha256", ""))
        for row in cases
        if isinstance(row, dict)
    ]
    record_fingerprints = [
        str((row.get("source") or {}).get("record_fingerprint_sha256", ""))
        for row in cases
        if isinstance(row, dict)
    ]
    model_identities = [
        str((row.get("source") or {}).get("model_identity_sha256", ""))
        for row in cases
        if isinstance(row, dict)
    ]
    if len(case_ids) != len(set(case_ids)):
        errors.append("duplicate_case_id")
    if len(lineages) != len(set(lineages)):
        errors.append("duplicate_lineage_credit")
    if len(source_hashes) != len(set(source_hashes)):
        errors.append("duplicate_source_sha256_credit")
    if len(record_fingerprints) != len(set(record_fingerprints)):
        errors.append("duplicate_record_fingerprint_credit")
    if len(model_identities) != len(set(model_identities)):
        errors.append("duplicate_model_identity_credit")
    case_contract_errors: dict[str, list[str]] = {}
    for row in cases:
        row_errors = _case_contract_errors(row)
        if row_errors:
            case_contract_errors[str(row.get("case_id", ""))] = row_errors
        if row.get("contract_pass") is not (not row_errors):
            errors.append(f"case_contract_mismatch:{row.get('case_id', '')}")
    expected_summary = {
        "target_independent_case_count": TARGET_CASE_COUNT,
        "available_independent_case_count": len(cases),
        "executed_case_count": len(cases),
        "clean_case_count": sum(row.get("corpus_class") == "clean" for row in cases),
        "dirty_case_count": sum(row.get("corpus_class") == "dirty" for row in cases),
        "case_contract_pass_count": sum(
            not _case_contract_errors(row) for row in cases
        ),
        "record_accounting_pass_count": sum(
            not _accounting_errors(row) for row in cases
        ),
        "silent_loss_negative_pass_count": sum(
            (row.get("negative_silent_loss_gate") or {}).get(
                "source_record_deletion_detected"
            )
            is True
            and (row.get("negative_silent_loss_gate") or {}).get(
                "accounting_record_deletion_detected"
            )
            is True
            for row in cases
        ),
        "rights_reviewed_case_count": sum(
            (row.get("provenance_and_rights") or {}).get(
                "redistribution_reviewed"
            )
            is True
            or (row.get("provenance_and_rights") or {}).get(
                "commercial_use_reviewed"
            )
            is True
            for row in cases
        ),
    }
    for key, expected in expected_summary.items():
        if summary.get(key) != expected:
            errors.append(f"summary_mismatch:{key}")
    source_binding = payload.get("source_binding")
    source_binding = source_binding if isinstance(source_binding, dict) else {}
    expected_source_binding_blockers: list[str] = []
    head_match = source_binding.get("declared_source_commit_sha") == source_binding.get(
        "observed_head_sha"
    )
    if source_binding.get("declared_source_commit_sha") != payload.get(
        "source_commit_sha"
    ):
        expected_source_binding_blockers.append("declared_source_commit_mismatch")
    if not head_match:
        expected_source_binding_blockers.append("head_source_commit_mismatch")
    if source_binding.get("source_tree_clean_required") is True and source_binding.get(
        "source_tree_clean"
    ) is not True:
        expected_source_binding_blockers.append("source_tree_not_clean")
    if source_binding.get("head_matches_declared_source") is not head_match:
        errors.append("source_binding_head_match_mismatch")
    if source_binding.get("blockers") != expected_source_binding_blockers:
        errors.append("source_binding_blockers_mismatch")
    if source_binding.get("contract_pass") is not (
        not expected_source_binding_blockers
    ):
        errors.append("source_binding_contract_mismatch")
    identity = payload.get("identity_gate")
    identity = identity if isinstance(identity, dict) else {}
    expected_identity_blockers: list[str] = []
    if len(case_ids) != len(set(case_ids)):
        expected_identity_blockers.append("duplicate_case_id")
    if len(lineages) != len(set(lineages)):
        expected_identity_blockers.append("duplicate_source_model_lineage_credit")
    if len(source_hashes) != len(set(source_hashes)):
        expected_identity_blockers.append("duplicate_source_sha256_credit")
    if len(record_fingerprints) != len(set(record_fingerprints)):
        expected_identity_blockers.append("duplicate_record_fingerprint_credit")
    if len(model_identities) != len(set(model_identities)):
        expected_identity_blockers.append("duplicate_model_identity_credit")
    identity_counts = {
        "unique_case_id_count": len(set(case_ids)),
        "unique_lineage_count": len(set(lineages)),
        "unique_source_sha256_count": len(set(source_hashes)),
        "unique_record_fingerprint_count": len(set(record_fingerprints)),
        "unique_model_identity_count": len(set(model_identities)),
    }
    for key, expected in identity_counts.items():
        if identity.get(key) != expected:
            errors.append(f"identity_count_mismatch:{key}")
    if identity.get("blockers") != expected_identity_blockers:
        errors.append("identity_blockers_mismatch")
    if identity.get("contract_pass") is not (not expected_identity_blockers):
        errors.append("identity_contract_mismatch")
    all_cases_pass = bool(cases) and not case_contract_errors
    technical_expected = bool(
        not expected_source_binding_blockers
        and not expected_identity_blockers
        and all_cases_pass
    )
    if payload.get("technical_available_set_contract_pass") is not technical_expected:
        errors.append("technical_available_set_contract_mismatch")
    target_gap = payload.get("target_gap")
    target_gap = target_gap if isinstance(target_gap, dict) else {}
    expected_target_blockers = _target_gap_blockers(
        case_count=len(cases),
        target_gap=target_gap,
    )
    target_expected = bool(technical_expected and not expected_target_blockers)
    if payload.get("target_10_case_contract_pass") is not target_expected:
        errors.append("target_10_case_contract_mismatch")
    expected_technical_blockers = list(expected_source_binding_blockers) + list(
        expected_identity_blockers
    )
    expected_technical_blockers.extend(
        f"case_contract_blocked:{case_id}" for case_id in case_contract_errors
    )
    if payload.get("technical_blockers") != sorted(set(expected_technical_blockers)):
        errors.append("technical_blockers_mismatch")
    if payload.get("target_blockers") != sorted(expected_target_blockers):
        errors.append("target_blockers_mismatch")
    expected_status = (
        "target_pass"
        if target_expected
        else "available_set_pass_target_blocked"
        if technical_expected
        else "technical_blocked"
    )
    if payload.get("status") != expected_status:
        errors.append("status_mismatch")
    claims = payload.get("claims")
    claims = claims if isinstance(claims, dict) else {}
    for claim in FALSE_AUTHORITY_CLAIMS:
        if claims.get(claim) is not False:
            errors.append(f"authority_claim_not_false:{claim}")
    if int(target_gap.get("missing_independent_case_count", -1)) != max(
        0, TARGET_CASE_COUNT - len(cases)
    ):
        errors.append("target_gap_count_mismatch")
    if len(cases) < TARGET_CASE_COUNT:
        if target_gap.get("blocker_id") != (
            "mgt_import_health_independent_source_10_missing"
        ):
            errors.append("target_gap_blocker_id_mismatch")
        for key in (
            "artifact_attached",
            "source_owner_identified",
            "rights_basis_recorded",
        ):
            if target_gap.get(key) is not False:
                errors.append(f"target_gap_not_false:{key}")
    elif len(cases) == TARGET_CASE_COUNT:
        if target_gap.get("blocker_id") is not None:
            errors.append("target_gap_blocker_not_cleared")
        for key in (
            "artifact_attached",
            "source_owner_identified",
            "rights_basis_recorded",
        ):
            if target_gap.get(key) is not True:
                errors.append(f"target_gap_not_true:{key}")
    if payload.get("raw_mgt_files_uploaded") is not False:
        errors.append("raw_mgt_upload_boundary_invalid")
    return sorted(set(errors))


def _target_gap_blockers(
    *, case_count: int, target_gap: dict[str, Any]
) -> list[str]:
    blockers: list[str] = []
    if case_count != TARGET_CASE_COUNT:
        blockers.append(
            f"independent_source_model_identity_shortfall:{case_count}/{TARGET_CASE_COUNT}"
        )
        blocker_id = target_gap.get("blocker_id")
        blockers.append(
            str(blocker_id)
            if isinstance(blocker_id, str) and blocker_id
            else "mgt_import_health_independent_source_10_missing"
        )
        return sorted(set(blockers))
    if target_gap.get("missing_independent_case_count") != 0:
        blockers.append("target_gap_missing_case_count_not_zero")
    if target_gap.get("blocker_id") is not None:
        blockers.append("target_gap_blocker_not_cleared")
    for key in (
        "artifact_attached",
        "source_owner_identified",
        "rights_basis_recorded",
    ):
        if target_gap.get(key) is not True:
            blockers.append(f"target_gap_condition_not_met:{key}")
    return sorted(set(blockers))


def _validated_evidence_dir(repo_root: Path, evidence_dir: Path) -> Path:
    if evidence_dir != DEFAULT_EVIDENCE_DIR:
        raise ReceiptError("custom_evidence_dir_not_supported")
    if (
        evidence_dir.is_absolute()
        or evidence_dir.as_posix() != DEFAULT_EVIDENCE_DIR.as_posix()
        or ".." in evidence_dir.parts
    ):
        raise ReceiptError("evidence_dir_unsafe")

    lexical_root = Path(os.path.abspath(repo_root))
    current = Path(lexical_root.anchor)
    for part in lexical_root.parts[1:]:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise ReceiptError("repository_root_unavailable") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ReceiptError(f"repository_path_symlink_forbidden:{current}")
    if not lexical_root.is_dir():
        raise ReceiptError("repository_root_not_directory")

    candidate = lexical_root
    for part in evidence_dir.parts:
        candidate /= part
        try:
            metadata = os.lstat(candidate)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ReceiptError("evidence_dir_ancestor_unreadable") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ReceiptError(f"evidence_dir_symlink_forbidden:{candidate}")
    try:
        candidate.relative_to(lexical_root)
    except ValueError as exc:
        raise ReceiptError("evidence_dir_outside_repo") from exc
    if candidate == lexical_root:
        raise ReceiptError("evidence_dir_must_not_be_repo_root")
    return candidate


def build_receipt(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    manifest_schema_path: Path = DEFAULT_MANIFEST_SCHEMA,
    receipt_schema_path: Path = DEFAULT_RECEIPT_SCHEMA,
    evidence_dir: Path = DEFAULT_EVIDENCE_DIR,
    require_clean_source: bool = True,
) -> dict[str, Any]:
    evidence_dir_abs = _validated_evidence_dir(repo_root, evidence_dir)
    repo_root = Path(os.path.abspath(repo_root))
    if COMMIT_RE.fullmatch(source_commit_sha) is None:
        raise ReceiptError("source_commit_sha_invalid")
    head_sha = _git_output(repo_root, "rev-parse", "HEAD")
    source_tree_clean = not bool(_git_output(repo_root, "status", "--porcelain"))
    manifest = _load_json(repo_root, manifest_path)
    _validate_schema(
        manifest,
        repo_root=repo_root,
        schema_path=manifest_schema_path,
        label="manifest",
    )
    if manifest.get("schema_version") != MANIFEST_VERSION:
        raise ReceiptError("manifest_schema_version_invalid")
    manifest_cases = manifest.get("cases")
    if not isinstance(manifest_cases, list):
        raise ReceiptError("manifest_cases_invalid")
    if os.path.lexists(evidence_dir_abs):
        if not stat.S_ISDIR(os.lstat(evidence_dir_abs).st_mode):
            raise ReceiptError("evidence_dir_existing_target_not_directory")
        shutil.rmtree(evidence_dir_abs)
    evidence_dir_abs.mkdir(parents=True)
    cases = [
        _case_receipt(
            repo_root=repo_root,
            manifest_case=row,
            evidence_dir=evidence_dir,
        )
        for row in manifest_cases
    ]
    case_ids = [row["case_id"] for row in cases]
    lineages = [row["lineage_id"] for row in cases]
    hashes = [row["source"]["observed_sha256"] for row in cases]
    record_fingerprints = [
        row["source"]["record_fingerprint_sha256"] for row in cases
    ]
    model_identities = [row["source"]["model_identity_sha256"] for row in cases]
    identity_blockers: list[str] = []
    if len(case_ids) != len(set(case_ids)):
        identity_blockers.append("duplicate_case_id")
    if len(lineages) != len(set(lineages)):
        identity_blockers.append("duplicate_source_model_lineage_credit")
    if len(hashes) != len(set(hashes)):
        identity_blockers.append("duplicate_source_sha256_credit")
    if len(record_fingerprints) != len(set(record_fingerprints)):
        identity_blockers.append("duplicate_record_fingerprint_credit")
    if len(model_identities) != len(set(model_identities)):
        identity_blockers.append("duplicate_model_identity_credit")
    if manifest.get("available_independent_case_count") != len(cases):
        raise ReceiptError("manifest_available_case_count_mismatch")
    source_binding_blockers: list[str] = []
    if head_sha != source_commit_sha:
        source_binding_blockers.append("head_source_commit_mismatch")
    if require_clean_source and not source_tree_clean:
        source_binding_blockers.append("source_tree_not_clean")
    source_binding = {
        "declared_source_commit_sha": source_commit_sha,
        "observed_head_sha": head_sha,
        "head_matches_declared_source": head_sha == source_commit_sha,
        "source_tree_clean": source_tree_clean,
        "source_tree_clean_required": require_clean_source,
        "contract_pass": not source_binding_blockers,
        "blockers": source_binding_blockers,
    }
    technical_blockers = list(source_binding_blockers) + identity_blockers
    technical_blockers.extend(
        f"case_contract_blocked:{row['case_id']}"
        for row in cases
        if row["contract_pass"] is not True
    )
    technical_available = not technical_blockers
    target_blockers = _target_gap_blockers(
        case_count=len(cases),
        target_gap=manifest["target_gap"],
    )
    target_pass = bool(technical_available and not target_blockers)
    summary = {
        "target_independent_case_count": TARGET_CASE_COUNT,
        "available_independent_case_count": len(cases),
        "executed_case_count": len(cases),
        "clean_case_count": sum(row["corpus_class"] == "clean" for row in cases),
        "dirty_case_count": sum(row["corpus_class"] == "dirty" for row in cases),
        "case_contract_pass_count": sum(row["contract_pass"] is True for row in cases),
        "record_accounting_pass_count": sum(not _accounting_errors(row) for row in cases),
        "silent_loss_negative_pass_count": sum(
            row["negative_silent_loss_gate"]["source_record_deletion_detected"]
            and row["negative_silent_loss_gate"][
                "accounting_record_deletion_detected"
            ]
            for row in cases
        ),
        "rights_reviewed_case_count": sum(
            row["provenance_and_rights"]["redistribution_reviewed"]
            or row["provenance_and_rights"]["commercial_use_reviewed"]
            for row in cases
        ),
    }
    runner_environment = (
        "github-hosted"
        if os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
        else "local"
    )
    payload = {
        "schema_version": RECEIPT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha,
        "execution_environment": runner_environment,
        "manifest": {
            "path": manifest_path.as_posix(),
            "sha256": _sha256(_resolve(repo_root, manifest_path)),
            "schema_path": manifest_schema_path.as_posix(),
            "schema_version": manifest["schema_version"],
        },
        "source_binding": source_binding,
        "identity_gate": {
            "credit_unit": "unique_source_or_model_lineage",
            "duplicate_sha256_credit_allowed": False,
            "derived_variant_credit_allowed": False,
            "unique_case_id_count": len(set(case_ids)),
            "unique_lineage_count": len(set(lineages)),
            "unique_source_sha256_count": len(set(hashes)),
            "unique_record_fingerprint_count": len(set(record_fingerprints)),
            "unique_model_identity_count": len(set(model_identities)),
            "contract_pass": not identity_blockers,
            "blockers": identity_blockers,
        },
        "summary": summary,
        "cases": cases,
        "technical_available_set_contract_pass": technical_available,
        "target_10_case_contract_pass": target_pass,
        "status": (
            "target_pass"
            if target_pass
            else "available_set_pass_target_blocked"
            if technical_available
            else "technical_blocked"
        ),
        "technical_blockers": sorted(set(technical_blockers)),
        "target_blockers": sorted(set(target_blockers)),
        "target_gap": manifest["target_gap"],
        "claims": {claim: False for claim in FALSE_AUTHORITY_CLAIMS},
        "raw_mgt_files_uploaded": False,
        "claim_boundary": (
            "A pass establishes current-source same-operator parser execution, visible "
            "record/entity accounting, and negative mutation detection for the available "
            "tracked MGT lineages only. Nine independent lineages do not satisfy the ten-case "
            "target. Dirty-case acceptance means unsupported or omitted rows are visible, not "
            "that they were losslessly imported. Solver/design, independent V&V, legal, "
            "redistribution, commercial-use, and release authority remain false."
        ),
    }
    _validate_schema(
        payload,
        repo_root=repo_root,
        schema_path=receipt_schema_path,
        label="receipt",
    )
    semantic_errors = validate_receipt_semantics(payload)
    if semantic_errors:
        raise ReceiptError(f"receipt_semantic_invalid:{semantic_errors[0]}")
    return payload


def _expected_entity_accounting_from_report(
    scan: dict[str, Any], report: dict[str, Any]
) -> dict[str, Any]:
    diagnostics = report.get("parser_diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    row_parse = diagnostics.get("row_parse")
    row_parse = row_parse if isinstance(row_parse, dict) else {}
    source_nodes = sorted(
        _leading_integer_ids(scan["section_rows"].get("NODE", []))
    )
    source_elements = sorted(
        _leading_integer_ids(scan["section_rows"].get("ELEMENT", []))
    )
    parser_contract_pass = report.get("contract_pass") is True
    parsed_nodes = int(row_parse.get("node_rows_parsed", 0) or 0)
    skipped_nodes = int(row_parse.get("node_rows_skipped", 0) or 0)
    parsed_elements = int(row_parse.get("element_rows_parsed", 0) or 0)
    skipped_elements = int(row_parse.get("element_rows_skipped", 0) or 0)
    if parser_contract_pass and skipped_nodes == 0:
        output_node_ids = source_nodes
    else:
        output_node_ids = []
    if parser_contract_pass and skipped_elements == 0:
        output_element_ids = source_elements
    else:
        output_element_ids = []
    return {
        "node": {
            "source_row_count": len(scan["section_rows"].get("NODE", [])),
            "source_id_count": len(source_nodes),
            "parser_reported_row_count": int(row_parse.get("node_rows", 0) or 0),
            "parser_reported_parsed_count": parsed_nodes,
            "parser_reported_skipped_count": skipped_nodes,
            "output_count": parsed_nodes if parser_contract_pass else 0,
            "source_id_sha256": _sha256_bytes(
                _json_text(source_nodes).encode("utf-8")
            ),
            "output_id_sha256": _sha256_bytes(
                _json_text(output_node_ids).encode("utf-8")
            ),
        },
        "element": {
            "source_row_count": len(
                scan["section_rows"].get("ELEMENT", [])
            ),
            "source_id_count": len(source_elements),
            "parser_reported_row_count": int(
                row_parse.get("element_rows", 0) or 0
            ),
            "parser_reported_parsed_count": parsed_elements,
            "parser_reported_skipped_count": skipped_elements,
            "output_count": parsed_elements if parser_contract_pass else 0,
            "source_id_sha256": _sha256_bytes(
                _json_text(source_elements).encode("utf-8")
            ),
            "output_id_sha256": _sha256_bytes(
                _json_text(output_element_ids).encode("utf-8")
            ),
        },
        "material": {
            "source_row_count": len(
                scan["section_rows"].get("MATERIAL", [])
            ),
            "parser_reported_row_count": int(
                row_parse.get("material_rows", 0) or 0
            ),
            "parser_reported_parsed_count": int(
                row_parse.get("material_rows_parsed", 0) or 0
            ),
        },
        "section": {
            "source_row_count": len(
                scan["section_rows"].get("SECTION", [])
            ),
            "parser_reported_row_count": int(
                row_parse.get("section_rows", 0) or 0
            ),
            "parser_reported_parsed_count": int(
                row_parse.get("section_rows_parsed", 0) or 0
            ),
        },
        "output_suppressed_by_parser_contract": not parser_contract_pass,
    }


def validate_receipt_artifact_bindings(
    payload: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    manifest_path: Path = DEFAULT_MANIFEST,
    manifest_schema_path: Path = DEFAULT_MANIFEST_SCHEMA,
    require_clean_source: bool = True,
) -> list[str]:
    """Recompute receipt bindings from tracked source and parser reports."""

    repo_root = repo_root.resolve()
    errors: list[str] = []
    try:
        manifest = _load_json(repo_root, manifest_path)
        manifest_schema = _load_json(repo_root, manifest_schema_path)
    except ReceiptError as exc:
        return [str(exc)]
    errors.extend(
        f"manifest_schema_invalid:{error}"
        for error in _schema_errors(manifest, manifest_schema)
    )
    manifest_sha = _sha256(_resolve(repo_root, manifest_path))
    manifest_binding = payload.get("manifest")
    manifest_binding = manifest_binding if isinstance(manifest_binding, dict) else {}
    expected_manifest_binding = {
        "path": manifest_path.as_posix(),
        "sha256": manifest_sha,
        "schema_path": manifest_schema_path.as_posix(),
        "schema_version": manifest.get("schema_version"),
    }
    if manifest_binding != expected_manifest_binding:
        errors.append("manifest_binding_mismatch")
    manifest_cases_raw = manifest.get("cases")
    manifest_cases = manifest_cases_raw if isinstance(manifest_cases_raw, list) else []
    receipt_cases_raw = payload.get("cases")
    receipt_cases = receipt_cases_raw if isinstance(receipt_cases_raw, list) else []
    manifest_case_ids = [
        str(row.get("case_id", "")) for row in manifest_cases if isinstance(row, dict)
    ]
    receipt_case_ids = [
        str(row.get("case_id", "")) for row in receipt_cases if isinstance(row, dict)
    ]
    if manifest_case_ids != receipt_case_ids:
        errors.append("manifest_receipt_case_sequence_mismatch")
    if manifest.get("available_independent_case_count") != len(manifest_cases):
        errors.append("manifest_available_case_count_mismatch")
    if manifest.get("target_independent_case_count") != TARGET_CASE_COUNT:
        errors.append("manifest_target_case_count_mismatch")
    if payload.get("target_gap") != manifest.get("target_gap"):
        errors.append("target_gap_manifest_binding_mismatch")
    manifest_by_case = {
        str(row.get("case_id", "")): row
        for row in manifest_cases
        if isinstance(row, dict)
    }
    receipt_projection_keys = (
        "lineage_id",
        "path",
        "corpus_class",
        "expected_parser_outcome",
    )
    provenance_keys = (
        "source_kind",
        "source_owner",
        "origin_url",
        "provenance_status",
        "rights_status",
        "redistribution_reviewed",
        "commercial_use_reviewed",
    )
    for case in receipt_cases:
        if not isinstance(case, dict):
            errors.append("receipt_case_not_object")
            continue
        case_id = str(case.get("case_id", ""))
        manifest_case = manifest_by_case.get(case_id)
        if manifest_case is None:
            errors.append(f"case_not_in_manifest:{case_id}")
            continue
        if any(
            case.get(key) != manifest_case.get(key) for key in receipt_projection_keys
        ):
            errors.append(f"case_manifest_projection_mismatch:{case_id}")
        expected_provenance = {
            key: manifest_case.get(key) for key in provenance_keys
        }
        if case.get("provenance_and_rights") != expected_provenance:
            errors.append(f"case_provenance_rights_binding_mismatch:{case_id}")
        source_rel = Path(str(manifest_case.get("path", "")))
        if source_rel.is_absolute() or ".." in source_rel.parts:
            errors.append(f"case_source_path_invalid:{case_id}")
            continue
        source_path = _resolve(repo_root, source_rel).resolve()
        try:
            source_path.relative_to(repo_root)
        except ValueError:
            errors.append(f"case_source_path_outside_repo:{case_id}")
            continue
        if not source_path.is_file():
            errors.append(f"case_source_missing:{case_id}")
            continue
        scan = _scan_source(source_path)
        expected_source = {
            "tracked": _git_tracked(repo_root, source_rel.as_posix()),
            "expected_sha256": manifest_case.get("expected_sha256"),
            "observed_sha256": _sha256(source_path),
            "expected_size_bytes": manifest_case.get("expected_size_bytes"),
            "observed_size_bytes": source_path.stat().st_size,
            "record_fingerprint_sha256": scan["record_fingerprint_sha256"],
            "model_identity_sha256": scan["model_identity_sha256"],
            "utf8_replacement_character_count": scan[
                "utf8_replacement_character_count"
            ],
        }
        if case.get("source") != expected_source:
            errors.append(f"case_source_binding_mismatch:{case_id}")
        expected_report_rel = (
            DEFAULT_EVIDENCE_DIR / "case-reports" / f"{case_id}.parser-report.json"
        )
        parser_row = case.get("parser")
        parser_row = parser_row if isinstance(parser_row, dict) else {}
        if parser_row.get("report_path") != expected_report_rel.as_posix():
            errors.append(f"case_parser_report_path_mismatch:{case_id}")
            continue
        report_path = _resolve(repo_root, expected_report_rel)
        if not report_path.is_file():
            errors.append(f"case_parser_report_missing:{case_id}")
            continue
        try:
            report = _load_json(repo_root, expected_report_rel)
        except ReceiptError:
            errors.append(f"case_parser_report_unreadable:{case_id}")
            continue
        report_contract_pass = report.get("contract_pass") is True
        expected_parser_row = {
            "script": PARSER.as_posix(),
            "return_code": 0 if report_contract_pass else 1,
            "return_code_matches_contract": True,
            "contract_pass": report_contract_pass,
            "reason_code": str(report.get("reason_code", "")),
            "report_path": expected_report_rel.as_posix(),
            "report_sha256": _sha256(report_path),
        }
        if parser_row != expected_parser_row:
            errors.append(f"case_parser_binding_mismatch:{case_id}")
        report_inputs = report.get("inputs")
        report_inputs = report_inputs if isinstance(report_inputs, dict) else {}
        expected_input_subset = {
            "mgt": source_rel.as_posix(),
            "forbid_synthetic_source": False,
            "min_nodes": 2,
            "min_elements": 1,
            "resolve_rigid_links": False,
            "drop_unreferenced_nodes": False,
            "strict_unknown_sections": False,
            "max_element_skip_count": 1000000,
            "max_element_skip_ratio": 1.0,
        }
        if any(
            report_inputs.get(key) != value
            for key, value in expected_input_subset.items()
        ):
            errors.append(f"case_parser_input_contract_mismatch:{case_id}")
        report_source = report.get("source_provenance")
        report_source = report_source if isinstance(report_source, dict) else {}
        if (
            report_source.get("path") != source_rel.as_posix()
            or report_source.get("sha256") != expected_source["observed_sha256"]
            or report_source.get("size_bytes") != expected_source["observed_size_bytes"]
        ):
            errors.append(f"case_parser_source_binding_mismatch:{case_id}")
        recognized = _recognized_section_counts(scan, report)
        visible_by_section = {
            key: int(count) - int(recognized.get(key, 0))
            for key, count in scan["section_row_counts"].items()
            if int(count) - int(recognized.get(key, 0)) > 0
        }
        expected_record = {
            "source_data_row_count": scan["data_row_count"],
            "parser_recognized_row_count": sum(recognized.values()),
            "visible_unsupported_or_omitted_row_count": sum(
                visible_by_section.values()
            ),
            "visible_unsupported_or_omitted_by_section": visible_by_section,
            "unaccounted_row_count": 0,
        }
        if case.get("record_accounting") != expected_record:
            errors.append(f"case_record_accounting_binding_mismatch:{case_id}")
        expected_entity = _expected_entity_accounting_from_report(scan, report)
        if case.get("entity_accounting") != expected_entity:
            errors.append(f"case_entity_accounting_binding_mismatch:{case_id}")
        expected_negative = _negative_silent_loss_gate(
            repo_root=repo_root,
            case_id=case_id,
            original_scan=scan,
            original_entity=expected_entity,
            original_sha256=expected_source["observed_sha256"],
            evidence_dir=DEFAULT_EVIDENCE_DIR,
        )
        if case.get("negative_silent_loss_gate") != expected_negative:
            errors.append(f"case_negative_gate_binding_mismatch:{case_id}")
    if require_clean_source:
        if _git_output(repo_root, "status", "--porcelain"):
            errors.append("source_tree_not_clean")
        if payload.get("source_binding", {}).get(
            "source_tree_clean_required"
        ) is not True:
            errors.append("source_tree_clean_requirement_disabled")
    return sorted(set(errors))


def check_receipt(
    *,
    repo_root: Path,
    source_commit_sha: str,
    receipt_path: Path,
    manifest_path: Path,
    manifest_schema_path: Path,
    receipt_schema_path: Path,
) -> tuple[bool, list[str]]:
    payload = _load_json(repo_root, receipt_path)
    errors = _schema_errors(payload, _load_json(repo_root, receipt_schema_path))
    errors.extend(validate_receipt_semantics(payload))
    errors.extend(
        validate_receipt_artifact_bindings(
            payload,
            repo_root=repo_root,
            manifest_path=manifest_path,
            manifest_schema_path=manifest_schema_path,
            require_clean_source=True,
        )
    )
    if payload.get("source_commit_sha") != source_commit_sha:
        errors.append("receipt_source_commit_mismatch")
    if _git_output(repo_root, "rev-parse", "HEAD") != source_commit_sha:
        errors.append("head_source_commit_mismatch")
    return not errors, sorted(set(errors))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit-sha", required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--manifest-schema", type=Path, default=DEFAULT_MANIFEST_SCHEMA
    )
    parser.add_argument("--schema", type=Path, default=DEFAULT_RECEIPT_SCHEMA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--allow-dirty-source", action="store_true")
    parser.add_argument("--fail-available-blocked", action="store_true")
    parser.add_argument("--fail-target-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.check:
        ok, errors = check_receipt(
            repo_root=ROOT,
            source_commit_sha=args.source_commit_sha,
            receipt_path=args.out,
            manifest_path=args.manifest,
            manifest_schema_path=args.manifest_schema,
            receipt_schema_path=args.schema,
        )
        print(
            "MGT import-health current-source check: "
            + ("pass" if ok else f"blocked | {','.join(errors)}")
        )
        return 0 if ok else 1
    payload = build_receipt(
        repo_root=ROOT,
        source_commit_sha=args.source_commit_sha,
        manifest_path=args.manifest,
        manifest_schema_path=args.manifest_schema,
        receipt_schema_path=args.schema,
        evidence_dir=DEFAULT_EVIDENCE_DIR,
        require_clean_source=not args.allow_dirty_source,
    )
    output = _resolve(ROOT, args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_json_text(payload), encoding="utf-8")
    print(
        "MGT import-health current source: "
        f"{payload['status']} | available="
        f"{payload['summary']['available_independent_case_count']}/"
        f"{payload['summary']['target_independent_case_count']} | "
        f"executed={payload['summary']['executed_case_count']} | "
        f"silent-loss={payload['summary']['silent_loss_negative_pass_count']}"
    )
    if args.fail_available_blocked and not payload[
        "technical_available_set_contract_pass"
    ]:
        return 1
    if args.fail_target_blocked and not payload["target_10_case_contract_pass"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
