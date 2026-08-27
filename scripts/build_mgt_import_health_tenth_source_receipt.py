#!/usr/bin/env python3
"""Build the runtime-acquired tenth-source MGT import-health receipt."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
CORE_SCRIPT = ROOT / "scripts/build_mgt_import_health_current_source_receipt.py"
DEFAULT_MANIFEST = Path("benchmarks/import_health/mgt_tenth_source_supplement.v1.json")
DEFAULT_MANIFEST_SCHEMA = Path(
    "canonical/mgt-import-health-tenth-source-manifest.v1.schema.json"
)
DEFAULT_RECEIPT_SCHEMA = Path(
    "canonical/mgt-import-health-tenth-source-technical-receipt.v1.schema.json"
)
DEFAULT_EVIDENCE_DIR = Path(".ci/mgt-import-health-tenth-source")
DEFAULT_OUTPUT = DEFAULT_EVIDENCE_DIR / "technical-receipt.json"
MANIFEST_VERSION = "mgt-import-health-tenth-source-manifest.v1"
RECEIPT_VERSION = "mgt-import-health-tenth-source-technical-receipt.v1"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
FALSE_AUTHORITY_CLAIMS = (
    "solver_ready_import",
    "design_authority",
    "independent_reproduction",
    "product_legal_approval",
    "redistribution_authority",
    "commercial_use_authority",
    "release_authority",
)
AUTHORITY_BLOCKERS = (
    "independent_operator_reproduction_missing",
    "release_authority_not_granted",
    "tenth_source_commercial_use_rights_unreviewed",
    "tenth_source_license_absent",
    "tenth_source_redistribution_rights_unreviewed",
)


class ReceiptError(ValueError):
    """Raised when evidence cannot be established fail-closed."""


def _load_core_module() -> Any:
    spec = importlib.util.spec_from_file_location("mgt_import_health_core", CORE_SCRIPT)
    if spec is None or spec.loader is None:
        raise ReceiptError("core_builder_import_failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CORE = _load_core_module()


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    final_url: str
    redirect_chain: tuple[str, ...]
    status_code: int
    content_length_header: int | None
    content_encoding: str
    body: bytes


Fetcher = Callable[[str, int], FetchResult]


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
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


def _git_blob_sha1(value: bytes) -> str:
    header = f"blob {len(value)}\0".encode("ascii")
    return hashlib.sha1(header + value, usedforsecurity=False).hexdigest()


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


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(  # type: ignore[override]
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Any:
        del req, fp, code, msg, headers, newurl
        raise ReceiptError("source_redirect_rejected")


def _network_fetch(url: str, maximum_size_bytes: int) -> FetchResult:
    request = Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "Accept-Encoding": "identity",
            "User-Agent": "structural-analysis-mgt-import-health/1",
        },
        method="GET",
    )
    opener = build_opener(_RejectRedirects())
    try:
        with opener.open(request, timeout=30) as response:
            status = int(response.getcode())
            final_url = str(response.geturl())
            content_encoding = str(response.headers.get("Content-Encoding", "identity"))
            length_raw = response.headers.get("Content-Length")
            content_length = int(length_raw) if length_raw is not None else None
            body = response.read(maximum_size_bytes + 1)
    except ReceiptError:
        raise
    except Exception as exc:
        raise ReceiptError(f"source_acquisition_failed:{exc.__class__.__name__}") from exc
    return FetchResult(
        requested_url=url,
        final_url=final_url,
        redirect_chain=(),
        status_code=status,
        content_length_header=content_length,
        content_encoding=content_encoding,
        body=body,
    )


def _expected_raw_url(case: dict[str, Any]) -> str:
    source_path = str(case.get("source_path", ""))
    if not source_path or source_path.startswith("/"):
        raise ReceiptError("source_path_invalid")
    path_parts = Path(source_path).parts
    if any(part in {"", ".", ".."} for part in path_parts):
        raise ReceiptError("source_path_invalid")
    repository = str(case.get("repository", ""))
    repo_parts = repository.split("/")
    if len(repo_parts) != 2 or not all(repo_parts):
        raise ReceiptError("source_repository_invalid")
    commit = str(case.get("source_commit_sha", ""))
    if COMMIT_RE.fullmatch(commit) is None:
        raise ReceiptError("source_commit_invalid")
    encoded_path = quote(source_path, safe="/")
    return f"https://raw.githubusercontent.com/{repository}/{commit}/{encoded_path}"


def _validate_exact_url(url: str, expected: str, *, label: str) -> None:
    if url != expected:
        raise ReceiptError(f"{label}_mismatch")
    parsed = urlsplit(url)
    expected_parsed = urlsplit(expected)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "raw.githubusercontent.com"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != expected_parsed.path
    ):
        raise ReceiptError(f"{label}_invalid")


def acquire_source(
    case: dict[str, Any], *, fetcher: Fetcher = _network_fetch
) -> tuple[dict[str, Any], bytes]:
    expected_url = _expected_raw_url(case)
    declared_url = str(case.get("raw_url", ""))
    _validate_exact_url(declared_url, expected_url, label="source_url")
    expected_size = int(case.get("expected_size_bytes", -1))
    if expected_size <= 0:
        raise ReceiptError("source_expected_size_invalid")
    expected_sha = str(case.get("expected_sha256", ""))
    if SHA256_RE.fullmatch(expected_sha) is None:
        raise ReceiptError("source_expected_sha256_invalid")
    expected_blob = str(case.get("expected_git_blob_sha1", ""))
    if SHA1_RE.fullmatch(expected_blob) is None:
        raise ReceiptError("source_expected_git_blob_sha1_invalid")

    result = fetcher(declared_url, expected_size)
    _validate_exact_url(result.requested_url, expected_url, label="requested_url")
    if result.redirect_chain:
        raise ReceiptError("source_redirect_rejected")
    _validate_exact_url(result.final_url, expected_url, label="final_url")
    if result.status_code != 200:
        raise ReceiptError("source_http_status_invalid")
    if result.content_encoding.lower() not in {"", "identity"}:
        raise ReceiptError("source_content_encoding_invalid")
    if result.content_length_header not in {None, expected_size}:
        raise ReceiptError("source_content_length_header_mismatch")
    body = result.body
    observed_size = len(body)
    observed_sha = _sha256_bytes(body)
    observed_blob = _git_blob_sha1(body)
    if observed_size != expected_size:
        raise ReceiptError("source_size_mismatch")
    if observed_sha != expected_sha:
        raise ReceiptError("source_sha256_mismatch")
    if observed_blob != expected_blob:
        raise ReceiptError("source_git_blob_sha1_mismatch")
    return (
        {
            "repository": case["repository"],
            "source_commit_sha": case["source_commit_sha"],
            "source_path": case["source_path"],
            "requested_url": result.requested_url,
            "final_url": result.final_url,
            "redirect_chain": list(result.redirect_chain),
            "http_status": result.status_code,
            "content_encoding": result.content_encoding or "identity",
            "content_length_header": result.content_length_header,
            "expected_size_bytes": expected_size,
            "observed_size_bytes": observed_size,
            "expected_sha256": expected_sha,
            "observed_sha256": observed_sha,
            "expected_git_blob_sha1": expected_blob,
            "observed_git_blob_sha1": observed_blob,
            "exact_commit_url_verified": True,
            "redirect_policy_verified": True,
            "content_integrity_verified": True,
            "raw_source_retained": False,
            "raw_source_uploaded": False,
        },
        body,
    )


def _external_case_errors(case: dict[str, Any], manifest_case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    acquisition = case.get("acquisition") or {}
    source = case.get("source_scan") or {}
    parser = case.get("parser") or {}
    record = case.get("record_accounting") or {}
    entity = case.get("entity_accounting") or {}
    negative = case.get("negative_silent_loss_gate") or {}
    rights = case.get("provenance_and_rights") or {}
    for key in (
        "exact_commit_url_verified",
        "redirect_policy_verified",
        "content_integrity_verified",
    ):
        if acquisition.get(key) is not True:
            errors.append(f"acquisition_{key}_not_true")
    for expected_key, observed_key in (
        ("expected_size_bytes", "observed_size_bytes"),
        ("expected_sha256", "observed_sha256"),
        ("expected_git_blob_sha1", "observed_git_blob_sha1"),
    ):
        if acquisition.get(expected_key) != acquisition.get(observed_key):
            errors.append(f"acquisition_{observed_key}_mismatch")
    try:
        expected_url = _expected_raw_url(manifest_case)
        _validate_exact_url(
            str(acquisition.get("requested_url", "")),
            expected_url,
            label="requested_url",
        )
        _validate_exact_url(
            str(acquisition.get("final_url", "")),
            expected_url,
            label="final_url",
        )
    except ReceiptError as exc:
        errors.append(str(exc))
    if acquisition.get("redirect_chain") != []:
        errors.append("source_redirect_rejected")
    if acquisition.get("raw_source_retained") is not False:
        errors.append("raw_source_retained")
    if acquisition.get("raw_source_uploaded") is not False:
        errors.append("raw_source_uploaded")
    expected_source = {
        "data_row_count": manifest_case.get("expected_data_row_count"),
        "visible_unsupported_or_omitted_row_count": manifest_case.get(
            "expected_visible_unsupported_or_omitted_row_count"
        ),
        "record_fingerprint_sha256": manifest_case.get(
            "expected_record_fingerprint_sha256"
        ),
        "model_identity_sha256": manifest_case.get(
            "expected_model_identity_sha256"
        ),
        "utf8_replacement_character_count": 0,
    }
    for key, expected in expected_source.items():
        if source.get(key) != expected:
            errors.append(f"source_scan_mismatch:{key}")
    if parser.get("return_code") != 0:
        errors.append("parser_return_code_nonzero")
    if parser.get("contract_pass") is not True:
        errors.append("parser_contract_blocked")
    if parser.get("reason_code") != "PASS":
        errors.append("parser_reason_not_pass")
    if case.get("observed_parser_outcome") != "pass":
        errors.append("parser_outcome_not_pass")
    if record.get("source_data_row_count") != manifest_case.get(
        "expected_data_row_count"
    ):
        errors.append("record_count_mismatch")
    if record.get("visible_unsupported_or_omitted_row_count") != 0:
        errors.append("visible_unsupported_rows_nonzero")
    if record.get("unaccounted_row_count") != 0:
        errors.append("unaccounted_rows_nonzero")
    accounting_shape = {
        "record_accounting": record,
        "entity_accounting": entity,
        "parser": parser,
    }
    try:
        errors.extend(CORE._accounting_errors(accounting_shape))
    except (KeyError, TypeError, ValueError):
        errors.append("accounting_shape_invalid")
    for family in ("node", "element"):
        family_row = entity.get(family) or {}
        if family_row.get("source_id_sha256") != family_row.get("output_id_sha256"):
            errors.append(f"{family}_normalized_id_mismatch")
    if negative.get("source_record_deletion_detected") is not True:
        errors.append("source_record_deletion_not_detected")
    if negative.get("accounting_record_deletion_detected") is not True:
        errors.append("accounting_record_deletion_not_detected")
    if rights.get("license_file_present") is not False:
        errors.append("license_presence_rewritten")
    if rights.get("redistribution_reviewed") is not False:
        errors.append("redistribution_review_unexpectedly_true")
    if rights.get("commercial_use_reviewed") is not False:
        errors.append("commercial_use_review_unexpectedly_true")
    return sorted(set(errors))


def _execute_tenth_case(
    *,
    repo_root: Path,
    manifest_case: dict[str, Any],
    evidence_dir: Path,
    fetcher: Fetcher,
) -> dict[str, Any]:
    acquisition, body = acquire_source(manifest_case, fetcher=fetcher)
    evidence_abs = _resolve(repo_root, evidence_dir)
    temporary_source_path: Path | None = None
    with tempfile.TemporaryDirectory(prefix="mgt-tenth-source-") as temporary_dir:
        temporary_source_path = Path(temporary_dir) / "source.mgt"
        temporary_source_path.write_bytes(body)
        scan = CORE._scan_source(temporary_source_path)
        report, model, return_code, report_path = CORE._run_parser(
            repo_root=repo_root,
            source_path=temporary_source_path.as_posix(),
            case_id=str(manifest_case["case_id"]),
            evidence_dir=evidence_dir,
        )
        recognized = CORE._recognized_section_counts(scan, report)
        visible_by_section = {
            key: int(count) - int(recognized.get(key, 0))
            for key, count in scan["section_row_counts"].items()
            if int(count) - int(recognized.get(key, 0)) > 0
        }
        recognized_total = sum(recognized.values())
        visible_total = sum(visible_by_section.values())
        entity = CORE._entity_accounting(scan, report, model)
        record = {
            "source_data_row_count": scan["data_row_count"],
            "parser_recognized_row_count": recognized_total,
            "visible_unsupported_or_omitted_row_count": visible_total,
            "visible_unsupported_or_omitted_by_section": visible_by_section,
            "unaccounted_row_count": int(
                scan["data_row_count"] - recognized_total - visible_total
            ),
        }
        accounting_shape = {
            "record_accounting": record,
            "entity_accounting": entity,
            "parser": {"contract_pass": report.get("contract_pass") is True},
        }
        mutated_sha, mutated_count = CORE._delete_first_data_record(scan)
        mutated_shape = deepcopy(accounting_shape)
        mutated_shape["entity_accounting"]["node"][
            "parser_reported_parsed_count"
        ] = max(
            0,
            int(
                mutated_shape["entity_accounting"]["node"][
                    "parser_reported_parsed_count"
                ]
            )
            - 1,
        )
        case = {
            "case_id": manifest_case["case_id"],
            "lineage_id": manifest_case["lineage_id"],
            "corpus_class": manifest_case["corpus_class"],
            "expected_parser_outcome": manifest_case["expected_parser_outcome"],
            "observed_parser_outcome": CORE._observed_outcome(
                parser_contract_pass=report.get("contract_pass") is True,
                visible_omitted_count=visible_total,
            ),
            "acquisition": acquisition,
            "source_scan": {
                "data_row_count": scan["data_row_count"],
                "visible_unsupported_or_omitted_row_count": visible_total,
                "record_fingerprint_sha256": scan[
                    "record_fingerprint_sha256"
                ],
                "model_identity_sha256": scan["model_identity_sha256"],
                "utf8_replacement_character_count": scan[
                    "utf8_replacement_character_count"
                ],
            },
            "provenance_and_rights": {
                key: manifest_case[key]
                for key in (
                    "source_owner",
                    "provenance_status",
                    "rights_status",
                    "license_file_present",
                    "redistribution_reviewed",
                    "commercial_use_reviewed",
                )
            },
            "parser": {
                "script": CORE.PARSER.as_posix(),
                "return_code": return_code,
                "contract_pass": report.get("contract_pass") is True,
                "reason_code": str(report.get("reason_code", "")),
                "report_path": report_path.as_posix(),
                "report_sha256": _sha256(_resolve(repo_root, report_path)),
            },
            "record_accounting": record,
            "entity_accounting": entity,
            "negative_silent_loss_gate": {
                "source_record_deletion_detected": bool(
                    mutated_sha != manifest_case["expected_sha256"]
                    and mutated_count == int(scan["data_row_count"]) - 1
                ),
                "accounting_record_deletion_detected": bool(
                    "node_parser_balance_mismatch"
                    in CORE._accounting_errors(mutated_shape)
                ),
                "source_mutation_reason": "source_sha256_and_record_count_mismatch",
                "accounting_mutation_reason": "node_parser_balance_mismatch",
            },
            "contract_pass": False,
            "blockers": [],
        }
        case_errors = _external_case_errors(case, manifest_case)
        case["contract_pass"] = not case_errors
        case["blockers"] = case_errors
    if temporary_source_path is None or temporary_source_path.exists():
        raise ReceiptError("temporary_raw_source_not_deleted")
    if any(
        path.is_file() and path.suffix.lower() != ".json"
        for path in evidence_abs.rglob("*")
    ):
        raise ReceiptError("non_json_evidence_artifact_detected")
    return case


def _copy_core_support(
    *, repo_root: Path, core_receipt: dict[str, Any], evidence_dir: Path
) -> list[dict[str, str]]:
    evidence_abs = _resolve(repo_root, evidence_dir)
    core_receipt_path = evidence_abs / "core-technical-receipt.json"
    core_receipt_path.write_text(_json_text(core_receipt), encoding="utf-8")
    rows = [
        {
            "role": "same_run_core_receipt",
            "path": core_receipt_path.relative_to(repo_root).as_posix(),
            "sha256": _sha256(core_receipt_path),
        }
    ]
    target_dir = evidence_abs / "core-case-reports"
    target_dir.mkdir(parents=True, exist_ok=True)
    for case in core_receipt["cases"]:
        source = _resolve(repo_root, Path(case["parser"]["report_path"]))
        target = target_dir / f"{case['case_id']}.parser-report.json"
        shutil.copyfile(source, target)
        rows.append(
            {
                "role": "same_run_core_parser_report",
                "path": target.relative_to(repo_root).as_posix(),
                "sha256": _sha256(target),
            }
        )
    return rows


def _case_identity_rows(
    core_receipt: dict[str, Any], tenth_case: dict[str, Any]
) -> list[dict[str, Any]]:
    rows = [
        {
            "case_id": case["case_id"],
            "lineage_id": case["lineage_id"],
            "source_sha256": case["source"]["observed_sha256"],
            "record_fingerprint_sha256": case["source"][
                "record_fingerprint_sha256"
            ],
            "model_identity_sha256": case["source"]["model_identity_sha256"],
            "contract_pass": case["contract_pass"],
        }
        for case in core_receipt["cases"]
    ]
    rows.append(
        {
            "case_id": tenth_case["case_id"],
            "lineage_id": tenth_case["lineage_id"],
            "source_sha256": tenth_case["acquisition"]["observed_sha256"],
            "record_fingerprint_sha256": tenth_case["source_scan"][
                "record_fingerprint_sha256"
            ],
            "model_identity_sha256": tenth_case["source_scan"][
                "model_identity_sha256"
            ],
            "contract_pass": tenth_case["contract_pass"],
        }
    )
    return rows


def _identity_gate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys = {
        "case_id": "unique_case_id_count",
        "lineage_id": "unique_lineage_count",
        "source_sha256": "unique_source_sha256_count",
        "record_fingerprint_sha256": "unique_record_fingerprint_count",
        "model_identity_sha256": "unique_model_identity_count",
    }
    blockers: list[str] = []
    counts: dict[str, int] = {}
    for key, count_key in keys.items():
        values = [str(row.get(key, "")) for row in rows]
        counts[count_key] = len(set(values))
        if len(values) != len(set(values)):
            blockers.append(f"duplicate_{key}_credit")
    return {
        **counts,
        "required_unique_count": 10,
        "contract_pass": len(rows) == 10 and not blockers,
        "blockers": blockers,
    }


def _support_artifact_rows(
    *, repo_root: Path, tenth_case: dict[str, Any], core_rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    report_path = _resolve(repo_root, Path(tenth_case["parser"]["report_path"]))
    return sorted(
        [
            *core_rows,
            {
                "role": "tenth_source_parser_report",
                "path": report_path.relative_to(repo_root).as_posix(),
                "sha256": _sha256(report_path),
            },
        ],
        key=lambda row: row["path"],
    )


def build_receipt(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    manifest_schema_path: Path = DEFAULT_MANIFEST_SCHEMA,
    receipt_schema_path: Path = DEFAULT_RECEIPT_SCHEMA,
    evidence_dir: Path = DEFAULT_EVIDENCE_DIR,
    require_clean_source: bool = True,
    fetcher: Fetcher = _network_fetch,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
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
        raise ReceiptError("manifest_version_invalid")
    evidence_abs = _resolve(repo_root, evidence_dir)
    if evidence_abs.exists():
        shutil.rmtree(evidence_abs)
    evidence_abs.mkdir(parents=True)

    core_receipt = CORE.build_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
        require_clean_source=require_clean_source,
    )
    core_artifact_errors = CORE.validate_receipt_artifact_bindings(
        core_receipt,
        repo_root=repo_root,
        require_clean_source=require_clean_source,
    )
    if core_artifact_errors:
        raise ReceiptError(f"core_receipt_invalid:{core_artifact_errors[0]}")
    if (
        core_receipt["technical_available_set_contract_pass"] is not True
        or core_receipt["summary"]["available_independent_case_count"] != 9
        or core_receipt["summary"]["executed_case_count"] != 9
    ):
        raise ReceiptError("core_nine_case_contract_blocked")
    core_support = _copy_core_support(
        repo_root=repo_root,
        core_receipt=core_receipt,
        evidence_dir=evidence_dir,
    )
    tenth_case = _execute_tenth_case(
        repo_root=repo_root,
        manifest_case=manifest["case"],
        evidence_dir=evidence_dir,
        fetcher=fetcher,
    )
    identity_rows = _case_identity_rows(core_receipt, tenth_case)
    identity = _identity_gate(identity_rows)
    support_rows = _support_artifact_rows(
        repo_root=repo_root,
        tenth_case=tenth_case,
        core_rows=core_support,
    )
    source_binding_blockers: list[str] = []
    if head_sha != source_commit_sha:
        source_binding_blockers.append("head_source_commit_mismatch")
    if require_clean_source and not source_tree_clean:
        source_binding_blockers.append("source_tree_not_clean")
    technical_blockers = list(source_binding_blockers)
    if tenth_case["contract_pass"] is not True:
        technical_blockers.append("tenth_source_case_contract_blocked")
    if identity["contract_pass"] is not True:
        technical_blockers.extend(identity["blockers"])
    technical_pass = not technical_blockers
    summary = {
        "target_independent_case_count": 10,
        "available_independent_case_count": 10,
        "executed_case_count": 10,
        "clean_case_count": int(core_receipt["summary"]["clean_case_count"]) + 1,
        "dirty_case_count": int(core_receipt["summary"]["dirty_case_count"]),
        "case_contract_pass_count": int(
            core_receipt["summary"]["case_contract_pass_count"]
        )
        + int(tenth_case["contract_pass"] is True),
        "record_accounting_pass_count": int(
            core_receipt["summary"]["record_accounting_pass_count"]
        )
        + int(not CORE._accounting_errors(tenth_case)),
        "silent_loss_negative_pass_count": int(
            core_receipt["summary"]["silent_loss_negative_pass_count"]
        )
        + int(
            tenth_case["negative_silent_loss_gate"][
                "source_record_deletion_detected"
            ]
            and tenth_case["negative_silent_loss_gate"][
                "accounting_record_deletion_detected"
            ]
        ),
        "rights_reviewed_case_count": 0,
    }
    runner_environment = (
        "github-hosted"
        if os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
        else "local"
    )
    core_receipt_path = evidence_abs / "core-technical-receipt.json"
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
        "source_binding": {
            "declared_source_commit_sha": source_commit_sha,
            "observed_head_sha": head_sha,
            "head_matches_declared_source": head_sha == source_commit_sha,
            "source_tree_clean": source_tree_clean,
            "source_tree_clean_required": require_clean_source,
            "contract_pass": not source_binding_blockers,
            "blockers": source_binding_blockers,
        },
        "same_run_core": {
            "receipt_path": core_receipt_path.relative_to(repo_root).as_posix(),
            "receipt_sha256": _sha256(core_receipt_path),
            "schema_version": core_receipt["schema_version"],
            "source_commit_sha": core_receipt["source_commit_sha"],
            "executed_case_count": core_receipt["summary"]["executed_case_count"],
            "technical_contract_pass": core_receipt[
                "technical_available_set_contract_pass"
            ],
            "target_10_case_contract_pass": core_receipt[
                "target_10_case_contract_pass"
            ],
        },
        "tenth_case": tenth_case,
        "case_identity_bindings": identity_rows,
        "identity_gate": identity,
        "summary": summary,
        "support_artifacts": support_rows,
        "technical_10_case_contract_pass": technical_pass,
        "status": (
            "technical_10_of_10_pass_authority_blocked"
            if technical_pass
            else "technical_blocked"
        ),
        "technical_blockers": sorted(set(technical_blockers)),
        "authority_blockers": list(AUTHORITY_BLOCKERS),
        "claims": {claim: False for claim in FALSE_AUTHORITY_CLAIMS},
        "raw_mgt_files_uploaded": False,
        "claim_boundary": (
            "A pass establishes same-run, current-source parser execution and visible "
            "record/entity accounting for ten technically independent MGT lineages, "
            "including runtime acquisition of the tenth source at an immutable public "
            "commit with exact SHA-256, byte length, and Git blob identity. The tenth "
            "repository has no recorded license, its raw bytes are neither retained nor "
            "uploaded, and independent reproduction, solver/design, legal, redistribution, "
            "commercial-use, and release authority all remain explicitly false."
        ),
    }
    _validate_schema(
        payload,
        repo_root=repo_root,
        schema_path=receipt_schema_path,
        label="receipt",
    )
    semantic_errors = validate_receipt_semantics(payload, manifest=manifest)
    if semantic_errors:
        raise ReceiptError(f"receipt_semantic_invalid:{semantic_errors[0]}")
    if any(path.is_file() and path.suffix.lower() != ".json" for path in evidence_abs.rglob("*")):
        raise ReceiptError("non_json_evidence_artifact_detected")
    return payload


def validate_receipt_semantics(
    payload: dict[str, Any], *, manifest: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    source_binding = payload.get("source_binding") or {}
    source_binding_blockers: list[str] = []
    if source_binding.get("declared_source_commit_sha") != payload.get(
        "source_commit_sha"
    ):
        source_binding_blockers.append("declared_source_commit_mismatch")
    if source_binding.get("observed_head_sha") != source_binding.get(
        "declared_source_commit_sha"
    ):
        source_binding_blockers.append("head_source_commit_mismatch")
    if source_binding.get("source_tree_clean_required") is True and source_binding.get(
        "source_tree_clean"
    ) is not True:
        source_binding_blockers.append("source_tree_not_clean")
    if source_binding.get("blockers") != source_binding_blockers:
        errors.append("source_binding_blockers_mismatch")
    if source_binding.get("contract_pass") is not (not source_binding_blockers):
        errors.append("source_binding_contract_mismatch")
    if source_binding.get("head_matches_declared_source") is not (
        source_binding.get("observed_head_sha")
        == source_binding.get("declared_source_commit_sha")
    ):
        errors.append("source_binding_head_match_mismatch")

    core = payload.get("same_run_core") or {}
    if core.get("source_commit_sha") != payload.get("source_commit_sha"):
        errors.append("core_source_commit_mismatch")
    if core.get("executed_case_count") != 9:
        errors.append("core_case_count_mismatch")
    if core.get("technical_contract_pass") is not True:
        errors.append("core_contract_blocked")
    if core.get("target_10_case_contract_pass") is not False:
        errors.append("core_honest_nine_case_boundary_invalid")

    tenth_case = payload.get("tenth_case") or {}
    if tenth_case.get("case_id") != manifest["case"]["case_id"]:
        errors.append("tenth_case_id_manifest_mismatch")
    case_errors = _external_case_errors(tenth_case, manifest["case"])
    if tenth_case.get("blockers") != case_errors:
        errors.append("tenth_case_blockers_mismatch")
    if tenth_case.get("contract_pass") is not (not case_errors):
        errors.append("tenth_case_contract_mismatch")
    acquisition = tenth_case.get("acquisition") or {}
    acquisition_keys = {
        "repository": "repository",
        "source_commit_sha": "source_commit_sha",
        "source_path": "source_path",
        "requested_url": "raw_url",
        "final_url": "raw_url",
        "expected_size_bytes": "expected_size_bytes",
        "expected_sha256": "expected_sha256",
        "expected_git_blob_sha1": "expected_git_blob_sha1",
    }
    for receipt_key, manifest_key in acquisition_keys.items():
        if acquisition.get(receipt_key) != manifest["case"].get(manifest_key):
            errors.append(f"tenth_acquisition_manifest_mismatch:{receipt_key}")
    rights_keys = (
        "source_owner",
        "provenance_status",
        "rights_status",
        "license_file_present",
        "redistribution_reviewed",
        "commercial_use_reviewed",
    )
    if (tenth_case.get("provenance_and_rights") or {}) != {
        key: manifest["case"][key] for key in rights_keys
    }:
        errors.append("tenth_rights_manifest_mismatch")

    identity_rows = payload.get("case_identity_bindings") or []
    expected_identity = _identity_gate(identity_rows)
    if payload.get("identity_gate") != expected_identity:
        errors.append("identity_gate_mismatch")
    if len(identity_rows) != 10:
        errors.append("identity_row_count_mismatch")
    if identity_rows:
        last = identity_rows[-1]
        expected_last = {
            "case_id": tenth_case.get("case_id"),
            "lineage_id": tenth_case.get("lineage_id"),
            "source_sha256": acquisition.get("observed_sha256"),
            "record_fingerprint_sha256": (tenth_case.get("source_scan") or {}).get(
                "record_fingerprint_sha256"
            ),
            "model_identity_sha256": (tenth_case.get("source_scan") or {}).get(
                "model_identity_sha256"
            ),
            "contract_pass": tenth_case.get("contract_pass"),
        }
        if last != expected_last:
            errors.append("tenth_identity_projection_mismatch")

    summary = payload.get("summary") or {}
    try:
        tenth_accounting_pass = not CORE._accounting_errors(tenth_case)
    except (KeyError, TypeError, ValueError):
        tenth_accounting_pass = False
    expected_summary = {
        "target_independent_case_count": 10,
        "available_independent_case_count": 10,
        "executed_case_count": 10,
        "clean_case_count": 3,
        "dirty_case_count": 7,
        "case_contract_pass_count": sum(
            row.get("contract_pass") is True for row in identity_rows
        ),
        "record_accounting_pass_count": 9 + int(tenth_accounting_pass),
        "silent_loss_negative_pass_count": 10
        if (tenth_case.get("negative_silent_loss_gate") or {}).get(
            "source_record_deletion_detected"
        )
        is True
        and (tenth_case.get("negative_silent_loss_gate") or {}).get(
            "accounting_record_deletion_detected"
        )
        is True
        else 9,
        "rights_reviewed_case_count": 0,
    }
    for key, expected in expected_summary.items():
        if summary.get(key) != expected:
            errors.append(f"summary_mismatch:{key}")

    technical_blockers = list(source_binding_blockers)
    if tenth_case.get("contract_pass") is not True:
        technical_blockers.append("tenth_source_case_contract_blocked")
    if expected_identity["contract_pass"] is not True:
        technical_blockers.extend(expected_identity["blockers"])
    technical_blockers = sorted(set(technical_blockers))
    if payload.get("technical_blockers") != technical_blockers:
        errors.append("technical_blockers_mismatch")
    technical_pass = not technical_blockers
    if payload.get("technical_10_case_contract_pass") is not technical_pass:
        errors.append("technical_contract_mismatch")
    expected_status = (
        "technical_10_of_10_pass_authority_blocked"
        if technical_pass
        else "technical_blocked"
    )
    if payload.get("status") != expected_status:
        errors.append("status_mismatch")
    if payload.get("authority_blockers") != list(AUTHORITY_BLOCKERS):
        errors.append("authority_blockers_mismatch")
    claims = payload.get("claims") or {}
    for claim in FALSE_AUTHORITY_CLAIMS:
        if claims.get(claim) is not False:
            errors.append(f"authority_claim_not_false:{claim}")
    if payload.get("raw_mgt_files_uploaded") is not False:
        errors.append("raw_mgt_upload_boundary_invalid")
    support = payload.get("support_artifacts") or []
    paths = [str(row.get("path", "")) for row in support if isinstance(row, dict)]
    if len(support) != 11:
        errors.append("support_artifact_count_mismatch")
    if len(paths) != len(set(paths)):
        errors.append("duplicate_support_artifact_path")
    roles = [str(row.get("role", "")) for row in support if isinstance(row, dict)]
    expected_role_counts = {
        "same_run_core_receipt": 1,
        "same_run_core_parser_report": 9,
        "tenth_source_parser_report": 1,
    }
    for role, expected_count in expected_role_counts.items():
        if roles.count(role) != expected_count:
            errors.append(f"support_artifact_role_count_mismatch:{role}")
    return sorted(set(errors))


def _replay_projection(case: dict[str, Any]) -> dict[str, Any]:
    projection = deepcopy(case)
    parser = projection.get("parser") or {}
    parser.pop("report_path", None)
    parser.pop("report_sha256", None)
    projection["parser"] = parser
    return projection


def validate_receipt_artifact_bindings(
    payload: dict[str, Any],
    *,
    repo_root: Path,
    manifest_path: Path = DEFAULT_MANIFEST,
    manifest_schema_path: Path = DEFAULT_MANIFEST_SCHEMA,
    require_clean_source: bool = True,
    replay_live_source: bool = False,
    fetcher: Fetcher = _network_fetch,
) -> list[str]:
    errors: list[str] = []
    try:
        manifest = _load_json(repo_root, manifest_path)
        _validate_schema(
            manifest,
            repo_root=repo_root,
            schema_path=manifest_schema_path,
            label="manifest",
        )
    except ReceiptError as exc:
        return [str(exc)]
    manifest_binding = payload.get("manifest") or {}
    if manifest_binding.get("path") != manifest_path.as_posix():
        errors.append("manifest_path_mismatch")
    if manifest_binding.get("sha256") != _sha256(_resolve(repo_root, manifest_path)):
        errors.append("manifest_sha256_mismatch")
    if manifest_binding.get("schema_path") != manifest_schema_path.as_posix():
        errors.append("manifest_schema_path_mismatch")
    errors.extend(validate_receipt_semantics(payload, manifest=manifest))

    for row in payload.get("support_artifacts") or []:
        if not isinstance(row, dict):
            errors.append("support_artifact_not_object")
            continue
        relative = Path(str(row.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts:
            errors.append("support_artifact_path_invalid")
            continue
        path = _resolve(repo_root, relative)
        if not path.is_file():
            errors.append(f"support_artifact_missing:{relative.as_posix()}")
            continue
        if path.suffix.lower() != ".json":
            errors.append(f"support_artifact_not_json:{relative.as_posix()}")
        if _sha256(path) != row.get("sha256"):
            errors.append(f"support_artifact_sha256_mismatch:{relative.as_posix()}")
        try:
            _load_json(repo_root, relative)
        except ReceiptError:
            errors.append(f"support_artifact_json_invalid:{relative.as_posix()}")

    core_binding = payload.get("same_run_core") or {}
    core_path = Path(str(core_binding.get("receipt_path", "")))
    try:
        core_receipt = _load_json(repo_root, core_path)
    except ReceiptError:
        errors.append("core_receipt_missing_or_invalid")
        core_receipt = None
    if core_receipt is not None:
        core_path_abs = _resolve(repo_root, core_path)
        if _sha256(core_path_abs) != core_binding.get("receipt_sha256"):
            errors.append("core_receipt_sha256_mismatch")
        core_schema = _load_json(repo_root, CORE.DEFAULT_RECEIPT_SCHEMA)
        if CORE._schema_errors(core_receipt, core_schema):
            errors.append("core_receipt_schema_invalid")
        if CORE.validate_receipt_semantics(core_receipt):
            errors.append("core_receipt_semantic_invalid")
        core_errors = CORE.validate_receipt_artifact_bindings(
            core_receipt,
            repo_root=repo_root,
            require_clean_source=require_clean_source,
        )
        errors.extend(f"core:{error}" for error in core_errors)
        expected_core_identities = _case_identity_rows(
            core_receipt, payload.get("tenth_case") or {}
        )[:-1]
        if (payload.get("case_identity_bindings") or [])[:9] != expected_core_identities:
            errors.append("core_identity_projection_mismatch")
        expected_support = {
            (
                "same_run_core_receipt",
                core_path.as_posix(),
                str(core_binding.get("receipt_sha256", "")),
            )
        }
        for case in core_receipt.get("cases") or []:
            expected_support.add(
                (
                    "same_run_core_parser_report",
                    (
                        core_path.parent
                        / "core-case-reports"
                        / f"{case['case_id']}.parser-report.json"
                    ).as_posix(),
                    str((case.get("parser") or {}).get("report_sha256", "")),
                )
            )
        tenth_parser = (payload.get("tenth_case") or {}).get("parser") or {}
        expected_support.add(
            (
                "tenth_source_parser_report",
                str(tenth_parser.get("report_path", "")),
                str(tenth_parser.get("report_sha256", "")),
            )
        )
        observed_support = {
            (
                str(row.get("role", "")),
                str(row.get("path", "")),
                str(row.get("sha256", "")),
            )
            for row in payload.get("support_artifacts") or []
            if isinstance(row, dict)
        }
        if observed_support != expected_support:
            errors.append("support_artifact_binding_mismatch")

    tenth_case = payload.get("tenth_case") or {}
    report_path = Path(str((tenth_case.get("parser") or {}).get("report_path", "")))
    report_abs = _resolve(repo_root, report_path)
    if not report_abs.is_file():
        errors.append("tenth_parser_report_missing")
    else:
        if _sha256(report_abs) != (tenth_case.get("parser") or {}).get(
            "report_sha256"
        ):
            errors.append("tenth_parser_report_sha256_mismatch")
        try:
            report = _load_json(repo_root, report_path)
        except ReceiptError:
            errors.append("tenth_parser_report_invalid")
        else:
            provenance = report.get("source_provenance") or {}
            acquisition = tenth_case.get("acquisition") or {}
            if provenance.get("sha256") != acquisition.get("observed_sha256"):
                errors.append("tenth_parser_source_sha256_mismatch")
            if provenance.get("size_bytes") != acquisition.get("observed_size_bytes"):
                errors.append("tenth_parser_source_size_mismatch")
            if report.get("contract_pass") is not True:
                errors.append("tenth_parser_report_contract_blocked")

    head_sha = _git_output(repo_root, "rev-parse", "HEAD")
    if head_sha != payload.get("source_commit_sha"):
        errors.append("head_source_commit_mismatch")
    if require_clean_source and _git_output(repo_root, "status", "--porcelain"):
        errors.append("source_tree_not_clean")
    if replay_live_source:
        replay_dir = Path(".ci/mgt-import-health-tenth-source-check")
        try:
            replay_case = _execute_tenth_case(
                repo_root=repo_root,
                manifest_case=manifest["case"],
                evidence_dir=replay_dir,
                fetcher=fetcher,
            )
            if _replay_projection(replay_case) != _replay_projection(tenth_case):
                errors.append("tenth_source_live_replay_mismatch")
        except ReceiptError as exc:
            errors.append(f"tenth_source_live_replay_failed:{exc}")
        finally:
            replay_abs = _resolve(repo_root, replay_dir)
            if replay_abs.exists():
                shutil.rmtree(replay_abs)
    return sorted(set(errors))


def check_receipt(
    *,
    repo_root: Path,
    source_commit_sha: str,
    receipt_path: Path,
    manifest_path: Path,
    manifest_schema_path: Path,
    receipt_schema_path: Path,
    fetcher: Fetcher = _network_fetch,
) -> tuple[bool, list[str]]:
    payload = _load_json(repo_root, receipt_path)
    errors = _schema_errors(payload, _load_json(repo_root, receipt_schema_path))
    errors.extend(
        validate_receipt_artifact_bindings(
            payload,
            repo_root=repo_root,
            manifest_path=manifest_path,
            manifest_schema_path=manifest_schema_path,
            require_clean_source=True,
            replay_live_source=True,
            fetcher=fetcher,
        )
    )
    if payload.get("source_commit_sha") != source_commit_sha:
        errors.append("receipt_source_commit_mismatch")
    return not errors, sorted(set(errors))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit-sha", required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--manifest-schema", type=Path, default=DEFAULT_MANIFEST_SCHEMA
    )
    parser.add_argument("--schema", type=Path, default=DEFAULT_RECEIPT_SCHEMA)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-dirty-source", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--fail-technical-blocked", action="store_true")
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
            "MGT import-health tenth-source check: "
            + ("pass" if ok else f"blocked | {','.join(errors)}")
        )
        return 0 if ok else 1
    payload = build_receipt(
        repo_root=ROOT,
        source_commit_sha=args.source_commit_sha,
        manifest_path=args.manifest,
        manifest_schema_path=args.manifest_schema,
        receipt_schema_path=args.schema,
        evidence_dir=args.evidence_dir,
        require_clean_source=not args.allow_dirty_source,
    )
    output = _resolve(ROOT, args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_json_text(payload), encoding="utf-8")
    print(
        "MGT import-health tenth source: "
        f"{payload['status']} | technical="
        f"{payload['summary']['case_contract_pass_count']}/10 | "
        f"silent-loss={payload['summary']['silent_loss_negative_pass_count']}/10 | "
        "rights=blocked"
    )
    if args.fail_technical_blocked and not payload[
        "technical_10_case_contract_pass"
    ]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
