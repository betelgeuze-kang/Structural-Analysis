"""Five-archetype medium benchmark corpus readiness contract.

This module is an evidence aggregator.  A source path, checksum, or parser
receipt is never promoted to numerical benchmark credit without the complete
per-case artifact chain and a valid PASS/REVIEW decision receipt.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from functools import lru_cache
import hashlib
from importlib import resources
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker

from .acceptance import (
    BENCHMARK_ACCEPTANCE_SCHEMA_VERSION,
    BENCHMARK_DECISION_SCHEMA_VERSION,
    inspect_benchmark_decision_receipt,
)


MEDIUM_BENCHMARK_CORPUS_SCHEMA_VERSION = "medium-benchmark-corpus-readiness.v1"
MEDIUM_BENCHMARK_CASE_SCHEMA_VERSION = "medium-benchmark-case-evidence.v1"
MEDIUM_BENCHMARK_EVIDENCE_BINDING_PROFILE = (
    "repository_bytes_and_receipt_payloads.v1"
)
MEDIUM_BENCHMARK_ARTIFACT_RECEIPT_SCHEMA_VERSION = (
    "medium-benchmark-artifact-receipt.v1"
)
MEDIUM_BENCHMARK_LICENSE_RECEIPT_SCHEMA_VERSION = (
    "medium-benchmark-source-license-receipt.v1"
)
MEDIUM_BENCHMARK_TOLERANCE_POLICY_SCHEMA_VERSION = (
    "medium-benchmark-tolerance-policy.v1"
)
_SHA256 = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_REFERENCE_SOLVER_CLASSES = frozenset({"open_source", "commercial"})

_ARTIFACT_RECEIPT_SCHEMA = (
    "medium_benchmark_artifact_receipt_v1.schema.json"
)
_LICENSE_RECEIPT_SCHEMA = (
    "medium_benchmark_source_license_receipt_v1.schema.json"
)
_TOLERANCE_POLICY_SCHEMA = (
    "medium_benchmark_tolerance_policy_v1.schema.json"
)
_ACCEPTANCE_SCHEMA = "benchmark_scientific_acceptance_v1.schema.json"
_DECISION_SCHEMA = "benchmark_scientific_decision_v1.schema.json"

_COMPARISON_METRIC_BY_ARTIFACT = {
    "residual_comparison": "residual_observation",
    "reaction_comparison": "reaction_equilibrium",
    "member_force_comparison": "member_force_local",
}

REQUIRED_CORE_METRIC_FAMILIES = (
    "displacement",
    "reaction_equilibrium",
    "member_force_local",
    "global_energy_norm",
    "residual_observation",
)

REQUIRED_CASE_ARTIFACTS = (
    "canonical_normalization_receipt",
    "reference_solver_input",
    "reference_output",
    "solver_output",
    "residual_comparison",
    "reaction_comparison",
    "member_force_comparison",
    "tolerance_policy",
    "decision_receipt",
)


@dataclass(frozen=True)
class MediumBenchmarkArchetype:
    archetype_id: str
    label: str
    required_capabilities: tuple[str, ...]
    claim_boundary: str


REQUIRED_MEDIUM_ARCHETYPES = (
    MediumBenchmarkArchetype(
        archetype_id="steel_moment_frame_3d",
        label="3D steel moment frame",
        required_capabilities=("frame_3d", "moment_connection", "multi_story"),
        claim_boundary="A frame-only building case; braced-only or 2D proxy cases do not fill this slot.",
    ),
    MediumBenchmarkArchetype(
        archetype_id="braced_frame_or_truss_tower",
        label="Braced frame / truss tower",
        required_capabilities=("axial_member", "bracing_or_truss", "three_dimensional"),
        claim_boundary="Requires a real braced or truss load path, not an axial-bar seed.",
    ),
    MediumBenchmarkArchetype(
        archetype_id="irregular_multistory_frame",
        label="Irregular multi-story frame",
        required_capabilities=(
            "frame_3d",
            "multi_story",
            "plan_or_vertical_irregularity",
        ),
        claim_boundary="Requires documented geometric or stiffness irregularity and medium scale.",
    ),
    MediumBenchmarkArchetype(
        archetype_id="frame_shell_diaphragm",
        label="Frame + shell diaphragm",
        required_capabilities=("frame_3d", "shell", "diaphragm_load_path"),
        claim_boundary="Parser-only shell presence does not prove shell force or diaphragm response accuracy.",
    ),
    MediumBenchmarkArchetype(
        archetype_id="foundation_link_or_mixed_element",
        label="Foundation/link or mixed-element model",
        required_capabilities=(
            "frame_or_shell",
            "link_spring_or_foundation",
            "mixed_element",
        ),
        claim_boundary="Requires an active link, spring, foundation, or mixed-element response in the reference outputs.",
    ),
)


def medium_benchmark_archetype_policy() -> list[dict[str, Any]]:
    """Return the immutable five-slot diversity policy as JSON-compatible rows."""

    rows = [asdict(row) for row in REQUIRED_MEDIUM_ARCHETYPES]
    for row in rows:
        row["required_capabilities"] = list(row["required_capabilities"])
    return rows


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return ()
    return value


def _valid_sha256(value: Any) -> bool:
    return bool(_SHA256.fullmatch(_text(value).lower()))


def _normalized_sha256(value: Any) -> str:
    text = _text(value).lower()
    if not _valid_sha256(text):
        return ""
    return text if text.startswith("sha256:") else f"sha256:{text}"


@lru_cache(maxsize=None)
def _schema_validator(schema_name: str) -> Draft202012Validator:
    schema = json.loads(
        resources.files("structural_analysis")
        .joinpath("schemas", schema_name)
        .read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _schema_contract_pass(payload: Any, schema_name: str) -> bool:
    return not list(_schema_validator(schema_name).iter_errors(payload))


def _relative_evidence_path(value: Any) -> Path | None:
    text = _text(value)
    if not text or "\\" in text:
        return None
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return Path(*path.parts)


def _bind_repository_file(
    *,
    repo_root: Path,
    path_value: Any,
    declared_sha256: Any,
    blocker_scope: str,
) -> tuple[dict[str, Any], bytes | None]:
    path_text = _text(path_value)
    declared_hash = _normalized_sha256(declared_sha256)
    blockers: list[str] = []
    relative = _relative_evidence_path(path_text)
    resolved: Path | None = None
    data: bytes | None = None
    observed_hash = ""
    byte_length: int | None = None
    root = repo_root.resolve()
    if relative is None:
        blockers.append(f"medium_case_{blocker_scope}_path_invalid")
    else:
        candidate = repo_root / relative
        if candidate.is_symlink():
            blockers.append(f"medium_case_{blocker_scope}_symlink_forbidden")
        try:
            resolved = candidate.resolve()
        except OSError:
            blockers.append(f"medium_case_{blocker_scope}_path_unresolvable")
        if resolved is not None and not resolved.is_relative_to(root):
            blockers.append(f"medium_case_{blocker_scope}_path_outside_root")
        elif resolved is not None and (not resolved.exists() or not resolved.is_file()):
            blockers.append(f"medium_case_{blocker_scope}_file_missing")
        elif resolved is not None:
            try:
                data = resolved.read_bytes()
            except OSError:
                blockers.append(f"medium_case_{blocker_scope}_file_unreadable")
            if data is not None:
                byte_length = len(data)
                observed_hash = f"sha256:{hashlib.sha256(data).hexdigest()}"
    if not declared_hash:
        blockers.append(f"medium_case_{blocker_scope}_sha256_invalid")
    elif observed_hash and observed_hash != declared_hash:
        blockers.append(f"medium_case_{blocker_scope}_sha256_mismatch")
    blockers = sorted(set(blockers))
    return (
        {
            "path": path_text,
            "declared_sha256": declared_hash,
            "observed_sha256": observed_hash,
            "byte_length": byte_length,
            "contract_pass": not blockers,
            "blockers": blockers,
        },
        data,
    )


def _json_payload(data: bytes | None) -> Mapping[str, Any] | None:
    if data is None:
        return None
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, Mapping) else None


def _valid_source_reference(value: Any) -> bool:
    text = _text(value)
    if not text:
        return False
    parsed = urlparse(text)
    return parsed.scheme in {"http", "https", "doi"} and bool(
        parsed.netloc or parsed.path
    )


def _artifact_blockers(name: str, value: Any) -> list[str]:
    payload = _safe_mapping(value)
    blockers: list[str] = []
    if not _text(payload.get("path")):
        blockers.append(f"medium_case_artifact_path_missing:{name}")
    if not _valid_sha256(payload.get("sha256")):
        blockers.append(f"medium_case_artifact_sha256_invalid:{name}")
    if payload.get("contract_pass") is not True:
        blockers.append(f"medium_case_artifact_contract_not_passed:{name}")
    return blockers


def _license_receipt_binding(
    *,
    repo_root: Path,
    case_id: str,
    source: Mapping[str, Any],
    license_declaration: Mapping[str, Any],
) -> dict[str, Any]:
    receipt_binding, receipt_bytes = _bind_repository_file(
        repo_root=repo_root,
        path_value=license_declaration.get("receipt_path"),
        declared_sha256=license_declaration.get("receipt_sha256"),
        blocker_scope="license_receipt",
    )
    blockers = list(receipt_binding["blockers"])
    payload = _json_payload(receipt_bytes)
    payload_schema_pass = bool(
        payload is not None
        and _schema_contract_pass(payload, _LICENSE_RECEIPT_SCHEMA)
    )
    if payload is None:
        if receipt_bytes is not None:
            blockers.append("medium_case_license_receipt_json_invalid")
    elif not payload_schema_pass:
        blockers.append("medium_case_license_receipt_schema_invalid")
    else:
        expected_pairs = (
            ("case_id", case_id),
            ("source_path", _text(source.get("path"))),
            ("source_sha256", _normalized_sha256(source.get("sha256"))),
            ("license_id", _text(license_declaration.get("id"))),
            ("spdx", _text(license_declaration.get("spdx"))),
            ("approval_status", _text(license_declaration.get("approval_status"))),
            (
                "local_execution_allowed",
                license_declaration.get("local_execution_allowed"),
            ),
            (
                "commercial_use_allowed",
                license_declaration.get("commercial_use_allowed"),
            ),
        )
        for field, expected in expected_pairs:
            actual = payload.get(field)
            if field in {"source_sha256"}:
                actual = _normalized_sha256(actual)
            if actual != expected:
                blockers.append(f"medium_case_license_receipt_{field}_mismatch")
        if payload.get("contract_pass") is not True or payload.get("blockers"):
            blockers.append("medium_case_license_receipt_contract_not_passed")
        approved_by = _text(payload.get("approved_by"))
        if not approved_by or approved_by.upper() in {"TBD", "UNKNOWN"}:
            blockers.append("medium_case_license_receipt_approver_missing")
    blockers = sorted(set(blockers))
    return {
        "schema_version": MEDIUM_BENCHMARK_LICENSE_RECEIPT_SCHEMA_VERSION,
        "receipt_file": receipt_binding,
        "payload_schema_contract_pass": payload_schema_pass,
        "contract_pass": not blockers,
        "blockers": blockers,
    }


def _artifact_payload_semantics(
    *,
    artifact_name: str,
    payload_bytes: bytes | None,
    media_type: str,
    case_id: str,
    metric_families: set[str],
    declared_decision: Mapping[str, Any],
) -> tuple[bool | None, list[str]]:
    blockers: list[str] = []
    semantic_pass: bool | None = None
    if artifact_name in {
        "canonical_normalization_receipt",
        "residual_comparison",
        "reaction_comparison",
        "member_force_comparison",
        "tolerance_policy",
        "decision_receipt",
    }:
        if media_type != "application/json":
            blockers.append(
                f"medium_case_artifact_payload_media_type_invalid:{artifact_name}"
            )
            return False, blockers
        payload = _json_payload(payload_bytes)
        if payload is None:
            blockers.append(f"medium_case_artifact_payload_json_invalid:{artifact_name}")
            return False, blockers
        if artifact_name == "canonical_normalization_receipt":
            semantic_pass = bool(
                payload.get("case_id") == case_id
                and payload.get("artifact_kind") == artifact_name
                and payload.get("contract_pass") is True
                and not payload.get("blockers")
            )
            if not semantic_pass:
                blockers.append(
                    "medium_case_canonical_normalization_payload_contract_not_passed"
                )
        elif artifact_name in _COMPARISON_METRIC_BY_ARTIFACT:
            expected_family = _COMPARISON_METRIC_BY_ARTIFACT[artifact_name]
            semantic_pass = bool(
                _schema_contract_pass(payload, _ACCEPTANCE_SCHEMA)
                and payload.get("schema_version")
                == BENCHMARK_ACCEPTANCE_SCHEMA_VERSION
                and payload.get("metric_family") == expected_family
                and payload.get("contract_pass") is True
            )
            if not semantic_pass:
                blockers.append(
                    f"medium_case_artifact_metric_contract_not_passed:{artifact_name}"
                )
        elif artifact_name == "tolerance_policy":
            semantic_pass = bool(
                _schema_contract_pass(payload, _TOLERANCE_POLICY_SCHEMA)
                and payload.get("case_id") == case_id
                and set(_safe_sequence(payload.get("metric_families")))
                == metric_families
                and payload.get("contract_pass") is True
                and not payload.get("blockers")
            )
            if not semantic_pass:
                blockers.append("medium_case_tolerance_policy_contract_not_passed")
        else:
            inspected = inspect_benchmark_decision_receipt(
                payload,
                required_metric_families=sorted(metric_families),
                require_benchmark_credit=True,
            )
            semantic_pass = bool(
                _schema_contract_pass(payload, _DECISION_SCHEMA)
                and inspected["contract_pass"]
                and dict(payload) == dict(declared_decision)
            )
            if not semantic_pass:
                blockers.append("medium_case_decision_receipt_payload_mismatch")
    return semantic_pass, blockers


def _artifact_receipt_binding(
    *,
    repo_root: Path,
    case_id: str,
    case_source_commit_sha: str,
    artifact_name: str,
    artifact_declaration: Mapping[str, Any],
    metric_families: set[str],
    declared_decision: Mapping[str, Any],
) -> dict[str, Any]:
    receipt_binding, receipt_bytes = _bind_repository_file(
        repo_root=repo_root,
        path_value=artifact_declaration.get("path"),
        declared_sha256=artifact_declaration.get("sha256"),
        blocker_scope=f"artifact_receipt:{artifact_name}",
    )
    blockers = list(receipt_binding["blockers"])
    receipt_payload = _json_payload(receipt_bytes)
    receipt_schema_pass = bool(
        receipt_payload is not None
        and _schema_contract_pass(receipt_payload, _ARTIFACT_RECEIPT_SCHEMA)
    )
    payload_binding: dict[str, Any] = {
        "path": "",
        "declared_sha256": "",
        "observed_sha256": "",
        "byte_length": None,
        "contract_pass": False,
        "blockers": [f"medium_case_artifact_payload_unbound:{artifact_name}"],
    }
    payload_semantic_pass: bool | None = None
    if receipt_payload is None:
        if receipt_bytes is not None:
            blockers.append(
                f"medium_case_artifact_receipt_json_invalid:{artifact_name}"
            )
    elif not receipt_schema_pass:
        blockers.append(
            f"medium_case_artifact_receipt_schema_invalid:{artifact_name}"
        )
    else:
        if receipt_payload.get("case_id") != case_id:
            blockers.append(
                f"medium_case_artifact_receipt_case_id_mismatch:{artifact_name}"
            )
        if receipt_payload.get("artifact_kind") != artifact_name:
            blockers.append(
                f"medium_case_artifact_receipt_kind_mismatch:{artifact_name}"
            )
        if receipt_payload.get("source_commit_sha") != case_source_commit_sha:
            blockers.append(
                f"medium_case_artifact_receipt_source_commit_mismatch:{artifact_name}"
            )
        if receipt_payload.get("contract_pass") is not True or receipt_payload.get(
            "blockers"
        ):
            blockers.append(
                f"medium_case_artifact_receipt_contract_not_passed:{artifact_name}"
            )
        payload_declaration = _safe_mapping(receipt_payload.get("payload"))
        payload_binding, payload_bytes = _bind_repository_file(
            repo_root=repo_root,
            path_value=payload_declaration.get("path"),
            declared_sha256=payload_declaration.get("sha256"),
            blocker_scope=f"artifact_payload:{artifact_name}",
        )
        blockers.extend(payload_binding["blockers"])
        declared_length = payload_declaration.get("byte_length")
        if (
            isinstance(declared_length, bool)
            or not isinstance(declared_length, int)
            or declared_length < 0
        ):
            blockers.append(
                f"medium_case_artifact_payload_byte_length_invalid:{artifact_name}"
            )
        elif payload_binding["byte_length"] != declared_length:
            blockers.append(
                f"medium_case_artifact_payload_byte_length_mismatch:{artifact_name}"
            )
        payload_semantic_pass, semantic_blockers = _artifact_payload_semantics(
            artifact_name=artifact_name,
            payload_bytes=payload_bytes,
            media_type=_text(payload_declaration.get("media_type")),
            case_id=case_id,
            metric_families=metric_families,
            declared_decision=declared_decision,
        )
        blockers.extend(semantic_blockers)
    blockers = sorted(set(blockers))
    return {
        "artifact_name": artifact_name,
        "schema_version": MEDIUM_BENCHMARK_ARTIFACT_RECEIPT_SCHEMA_VERSION,
        "receipt_file": receipt_binding,
        "receipt_schema_contract_pass": receipt_schema_pass,
        "payload_file": payload_binding,
        "payload_semantic_contract_pass": payload_semantic_pass,
        "source_commit_sha": _text(
            receipt_payload.get("source_commit_sha")
            if receipt_payload is not None
            else ""
        ),
        "contract_pass": not blockers,
        "blockers": blockers,
    }


def _timezone_aware_timestamp(value: Any) -> bool:
    text = _text(value)
    if not text:
        return False
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _scientific_decision_blockers(
    decision: Mapping[str, Any],
    *,
    declared_metric_families: set[str],
) -> list[str]:
    blockers: list[str] = []
    normalized_decision = _text(decision.get("decision")).upper()
    decision_metric_families = [
        _text(value)
        for value in _safe_sequence(decision.get("metric_families"))
        if _text(value)
    ]
    if decision.get("schema_version") != BENCHMARK_DECISION_SCHEMA_VERSION:
        blockers.append("medium_case_scientific_decision_schema_invalid")
    if normalized_decision not in {"PASS", "REVIEW"}:
        blockers.append("medium_case_decision_not_pass_or_review")
    if decision.get("decision_contract_pass") is not True:
        blockers.append("medium_case_decision_contract_not_passed")
    if decision.get("benchmark_credit") is not True:
        blockers.append("medium_case_pass_or_review_credit_missing")
    if decision.get("hard_blockers"):
        blockers.append("medium_case_scientific_decision_hard_blockers_present")
    if decision.get("decision_blockers"):
        blockers.append("medium_case_scientific_decision_blockers_present")
    if decision.get("metric_family_count") != len(decision_metric_families):
        blockers.append("medium_case_scientific_decision_metric_count_mismatch")
    if len(decision_metric_families) != len(set(decision_metric_families)):
        blockers.append("medium_case_scientific_decision_metric_duplicate")
    if set(decision_metric_families) != declared_metric_families:
        blockers.append("medium_case_scientific_decision_metric_scope_mismatch")
    if not _timezone_aware_timestamp(decision.get("evaluated_at")):
        blockers.append("medium_case_scientific_decision_evaluated_at_invalid")
    review = _safe_mapping(decision.get("review"))
    if normalized_decision == "PASS":
        if decision.get("numerical_pass") is not True:
            blockers.append("medium_case_scientific_pass_without_numerical_pass")
        if review:
            blockers.append("medium_case_scientific_pass_review_must_be_null")
    elif normalized_decision == "REVIEW":
        if not review:
            blockers.append("medium_case_scientific_review_missing")
        else:
            if review.get("contract_pass") is not True:
                blockers.append("medium_case_scientific_review_contract_not_passed")
            if not _text(review.get("engineer_id")):
                blockers.append("medium_case_scientific_review_engineer_id_missing")
            if not _text(review.get("reason")):
                blockers.append("medium_case_scientific_review_reason_missing")
            if not _safe_sequence(review.get("scope")):
                blockers.append("medium_case_scientific_review_scope_missing")
            if not _text(review.get("evidence_ref")):
                blockers.append("medium_case_scientific_review_evidence_ref_missing")
            for field in ("approved_at", "expires_at"):
                if not _timezone_aware_timestamp(review.get(field)):
                    blockers.append(f"medium_case_scientific_review_{field}_invalid")
    return blockers


def inspect_medium_benchmark_case(
    case: Any,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Inspect one case and require repository-bound evidence bytes for credit."""

    payload = _safe_mapping(case)
    blockers: list[str] = []
    case_id = _text(payload.get("case_id"))
    archetype_id = _text(payload.get("archetype_id"))
    source_family = _text(payload.get("source_family"))
    if payload.get("schema_version") != MEDIUM_BENCHMARK_CASE_SCHEMA_VERSION:
        blockers.append("medium_case_schema_version_invalid")
    blockers.extend(
        _text(value)
        for value in _safe_sequence(payload.get("declared_blockers"))
        if _text(value)
    )
    if not case_id:
        blockers.append("medium_case_id_missing")
    valid_archetypes = {row.archetype_id: row for row in REQUIRED_MEDIUM_ARCHETYPES}
    archetype = valid_archetypes.get(archetype_id)
    if archetype is None:
        blockers.append("medium_case_archetype_invalid")
    if _text(payload.get("size_class")) != "medium":
        blockers.append("medium_case_size_class_not_medium")
    if not _text(payload.get("medium_scale_basis")):
        blockers.append("medium_case_scale_basis_missing")
    if not source_family:
        blockers.append("medium_case_source_family_missing")

    capabilities = {
        _text(value)
        for value in _safe_sequence(payload.get("capabilities"))
        if _text(value)
    }
    if archetype is not None:
        missing_capabilities = sorted(
            set(archetype.required_capabilities) - capabilities
        )
        blockers.extend(
            f"medium_case_capability_missing:{capability}"
            for capability in missing_capabilities
        )

    source = _safe_mapping(payload.get("source"))
    if not _text(source.get("path")):
        blockers.append("medium_case_source_path_missing")
    if not _valid_source_reference(source.get("url_or_doi")):
        blockers.append("medium_case_source_url_or_doi_invalid")
    if not _valid_sha256(source.get("sha256")):
        blockers.append("medium_case_source_sha256_invalid")
    license_receipt = _safe_mapping(source.get("license"))
    if not _text(license_receipt.get("id")):
        blockers.append("medium_case_license_id_missing")
    if not _text(license_receipt.get("spdx")):
        blockers.append("medium_case_license_spdx_missing")
    if license_receipt.get("approval_status") != "approved":
        blockers.append("medium_case_license_not_approved")
    if license_receipt.get("local_execution_allowed") is not True:
        blockers.append("medium_case_local_execution_not_approved")
    if license_receipt.get("commercial_use_allowed") is not True:
        blockers.append("medium_case_commercial_use_not_approved")

    reference_solver = _safe_mapping(payload.get("reference_solver"))
    reference_solver_name = _text(reference_solver.get("name"))
    reference_solver_class = _text(reference_solver.get("solver_class"))
    if not reference_solver_name:
        blockers.append("medium_case_reference_solver_name_missing")
    if not _text(reference_solver.get("version")):
        blockers.append("medium_case_reference_solver_version_missing")
    if reference_solver.get("version_verified") is not True:
        blockers.append("medium_case_reference_solver_version_unverified")
    if reference_solver_class not in _REFERENCE_SOLVER_CLASSES:
        blockers.append("medium_case_reference_solver_class_invalid")
    if reference_solver.get("independent_from_product") is not True:
        blockers.append("medium_case_reference_solver_not_independent")

    artifacts = _safe_mapping(payload.get("artifacts"))
    for artifact_name in REQUIRED_CASE_ARTIFACTS:
        blockers.extend(_artifact_blockers(artifact_name, artifacts.get(artifact_name)))

    metric_families = {
        _text(value)
        for value in _safe_sequence(payload.get("metric_families"))
        if _text(value)
    }
    blockers.extend(
        f"medium_case_metric_family_missing:{family}"
        for family in sorted(set(REQUIRED_CORE_METRIC_FAMILIES) - metric_families)
    )

    decision = _safe_mapping(payload.get("decision"))
    blockers.extend(
        _scientific_decision_blockers(
            decision,
            declared_metric_families=metric_families,
        )
    )

    source_commit_sha = _text(payload.get("source_commit_sha")).lower()
    binding_blockers: list[str] = []
    source_file_binding: dict[str, Any] = {
        "path": _text(source.get("path")),
        "declared_sha256": _normalized_sha256(source.get("sha256")),
        "observed_sha256": "",
        "byte_length": None,
        "contract_pass": False,
        "blockers": ["medium_case_evidence_root_missing"],
    }
    license_binding: dict[str, Any] = {
        "schema_version": MEDIUM_BENCHMARK_LICENSE_RECEIPT_SCHEMA_VERSION,
        "receipt_file": {
            "path": _text(license_receipt.get("receipt_path")),
            "declared_sha256": _normalized_sha256(
                license_receipt.get("receipt_sha256")
            ),
            "observed_sha256": "",
            "byte_length": None,
            "contract_pass": False,
            "blockers": ["medium_case_evidence_root_missing"],
        },
        "payload_schema_contract_pass": False,
        "contract_pass": False,
        "blockers": ["medium_case_evidence_root_missing"],
    }
    artifact_binding_rows: list[dict[str, Any]] = []
    if not _COMMIT_SHA.fullmatch(source_commit_sha):
        binding_blockers.append("medium_case_source_commit_sha_invalid")
    if repo_root is None:
        binding_blockers.append("medium_case_evidence_root_missing")
    else:
        source_file_binding, _source_bytes = _bind_repository_file(
            repo_root=repo_root,
            path_value=source.get("path"),
            declared_sha256=source.get("sha256"),
            blocker_scope="source",
        )
        binding_blockers.extend(source_file_binding["blockers"])
        license_binding = _license_receipt_binding(
            repo_root=repo_root,
            case_id=case_id,
            source=source,
            license_declaration=license_receipt,
        )
        binding_blockers.extend(license_binding["blockers"])
        artifact_binding_rows = [
            _artifact_receipt_binding(
                repo_root=repo_root,
                case_id=case_id,
                case_source_commit_sha=source_commit_sha,
                artifact_name=artifact_name,
                artifact_declaration=_safe_mapping(artifacts.get(artifact_name)),
                metric_families=metric_families,
                declared_decision=decision,
            )
            for artifact_name in REQUIRED_CASE_ARTIFACTS
        ]
        binding_blockers.extend(
            blocker
            for row in artifact_binding_rows
            for blocker in row["blockers"]
        )
    evidence_binding_contract_pass = bool(
        not binding_blockers
        and source_file_binding["contract_pass"]
        and license_binding["contract_pass"]
        and len(artifact_binding_rows) == len(REQUIRED_CASE_ARTIFACTS)
        and all(row["contract_pass"] for row in artifact_binding_rows)
    )
    blockers.extend(binding_blockers)

    blockers = sorted(set(blockers))
    return {
        "schema_version": MEDIUM_BENCHMARK_CASE_SCHEMA_VERSION,
        "case_id": case_id,
        "archetype_id": archetype_id,
        "size_class": _text(payload.get("size_class")),
        "medium_scale_basis": _text(payload.get("medium_scale_basis")),
        "capabilities": sorted(capabilities),
        "source_family": source_family,
        "source_path": _text(source.get("path")),
        "source_url_or_doi": _text(source.get("url_or_doi")),
        "source_sha256": _text(source.get("sha256")),
        "source_commit_sha": source_commit_sha,
        "reference_solver_name": reference_solver_name,
        "reference_solver_class": reference_solver_class,
        "metric_families": sorted(metric_families),
        "decision_schema_version": _text(decision.get("schema_version")),
        "decision": _text(decision.get("decision")).upper(),
        "decision_metric_families": sorted(
            {
                _text(value)
                for value in _safe_sequence(decision.get("metric_families"))
                if _text(value)
            }
        ),
        "evidence_binding_profile": MEDIUM_BENCHMARK_EVIDENCE_BINDING_PROFILE,
        "source_file_binding": source_file_binding,
        "license_receipt_binding": license_binding,
        "artifact_receipt_bindings": artifact_binding_rows,
        "bound_artifact_receipt_count": sum(
            1 for row in artifact_binding_rows if row["contract_pass"]
        ),
        "evidence_binding_contract_pass": evidence_binding_contract_pass,
        "blockers": blockers,
        "ready_for_medium_benchmark_credit": not blockers,
        "claim_boundary": (
            "This row verifies repository-contained source, license receipt, artifact "
            "receipt, and payload bytes plus selected scientific payload semantics. It "
            "does not authenticate external solver execution, legal authority, or the "
            "human identities declared by those bound receipts."
        ),
    }


def build_medium_benchmark_corpus_readiness(
    cases: Any,
    *,
    repo_root: Path | None = None,
    input_blockers: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a non-promoting readiness view over the five required archetypes."""

    case_values = _safe_sequence(cases)
    case_rows = [
        inspect_medium_benchmark_case(case, repo_root=repo_root)
        for case in case_values
    ]
    normalized_input_blockers = sorted(
        {_text(value) for value in input_blockers if _text(value)}
    )
    blockers: list[str] = list(normalized_input_blockers)
    case_ids = [row["case_id"] for row in case_rows if row["case_id"]]
    duplicate_case_ids = sorted(
        case_id for case_id in set(case_ids) if case_ids.count(case_id) > 1
    )
    blockers.extend(
        f"medium_corpus_duplicate_case_id:{case_id}" for case_id in duplicate_case_ids
    )

    slot_rows: list[dict[str, Any]] = []
    for archetype in REQUIRED_MEDIUM_ARCHETYPES:
        selected = [
            row for row in case_rows if row["archetype_id"] == archetype.archetype_id
        ]
        if not selected:
            slot_status = "operator_selection_required"
            slot_blockers = [
                f"medium_corpus_archetype_missing:{archetype.archetype_id}"
            ]
        elif len(selected) > 1:
            slot_status = "duplicate_selection_blocked"
            slot_blockers = [
                f"medium_corpus_archetype_duplicate:{archetype.archetype_id}"
            ]
        elif selected[0]["ready_for_medium_benchmark_credit"]:
            slot_status = "ready_for_credit"
            slot_blockers = []
        else:
            slot_status = "selected_blocked"
            slot_blockers = list(selected[0]["blockers"])
        blockers.extend(slot_blockers)
        slot_rows.append(
            {
                "archetype_id": archetype.archetype_id,
                "label": archetype.label,
                "required_capabilities": list(archetype.required_capabilities),
                "selected_case_ids": [row["case_id"] for row in selected],
                "slot_status": slot_status,
                "blockers": slot_blockers,
                "claim_boundary": archetype.claim_boundary,
            }
        )

    ready_rows = [row for row in case_rows if row["ready_for_medium_benchmark_credit"]]
    solver_names = sorted(
        {
            row["reference_solver_name"]
            for row in ready_rows
            if row["reference_solver_name"]
        }
    )
    normalized_solver_names = {name.casefold() for name in solver_names}
    opensees_present = any("opensees" in name for name in normalized_solver_names)
    second_solver_present = any(
        "opensees" not in name for name in normalized_solver_names
    )
    if not opensees_present:
        blockers.append("medium_corpus_opensees_reference_missing")
    if not second_solver_present:
        blockers.append("medium_corpus_second_reference_solver_missing")

    ready_source_families = {
        row["source_family"] for row in ready_rows if row["source_family"]
    }
    if len(ready_source_families) < 2:
        blockers.append("medium_corpus_source_family_diversity_below_two")

    credit_count = sum(
        1 for row in slot_rows if row["slot_status"] == "ready_for_credit"
    )
    blockers = sorted(set(blockers))
    contract_pass = credit_count == len(REQUIRED_MEDIUM_ARCHETYPES) and not blockers
    return {
        "schema_version": MEDIUM_BENCHMARK_CORPUS_SCHEMA_VERSION,
        "status": "pass" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "required_case_count": len(REQUIRED_MEDIUM_ARCHETYPES),
        "attached_case_count": len(case_rows),
        "medium_benchmark_credit_count": credit_count,
        "required_core_metric_families": list(REQUIRED_CORE_METRIC_FAMILIES),
        "required_case_artifacts": list(REQUIRED_CASE_ARTIFACTS),
        "evidence_binding_profile": MEDIUM_BENCHMARK_EVIDENCE_BINDING_PROFILE,
        "evidence_binding_required": True,
        "byte_bound_case_count": sum(
            1 for row in case_rows if row["evidence_binding_contract_pass"]
        ),
        "archetype_policy": medium_benchmark_archetype_policy(),
        "slot_rows": slot_rows,
        "case_rows": case_rows,
        "reference_solver_diversity": {
            "solver_names": solver_names,
            "opensees_present": opensees_present,
            "second_independent_solver_present": second_solver_present,
            "contract_pass": opensees_present and second_solver_present,
        },
        "source_family_count": len(ready_source_families),
        "input_blockers": normalized_input_blockers,
        "blockers": blockers,
        "summary_line": (
            f"Medium benchmark corpus: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"credit={credit_count}/{len(REQUIRED_MEDIUM_ARCHETYPES)} | "
            f"reference_solvers={len(solver_names)}"
        ),
        "claim_boundary": (
            "This readiness object requires five structurally distinct medium cases and "
            "repository-bound metric-specific evidence. Missing bytes, hash mismatches, "
            "path escapes, missing slots, parser-only artifacts, unapproved licenses, "
            "template reviews, and large-model substitutes receive zero credit. A PASS "
            "still does not authenticate external execution or grant release or "
            "final-design authority."
        ),
    }
