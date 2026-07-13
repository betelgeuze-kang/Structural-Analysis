"""Immutable schema-validated audit envelope for MGT to ModelIR v2 imports."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib import resources
import json
from typing import Any

from jsonschema import Draft202012Validator


MGT_MODEL_IR_V2_AUDIT_SCHEMA_VERSION = (
    "structural-analysis-mgt-model-ir-v2-audit.v1"
)


@dataclass(frozen=True)
class MGTImportAudit:
    schema_version: str
    status: str
    canonical_json: str
    content_hash: str

    def __post_init__(self) -> None:
        try:
            payload = json.loads(self.canonical_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise MGTImportAuditValidationError((f"/: invalid canonical JSON: {exc}",)) from exc
        issues = validate_mgt_import_audit(payload)
        if issues:
            raise MGTImportAuditValidationError(issues)
        if not isinstance(payload, dict):  # pragma: no cover - schema invariant
            raise MGTImportAuditValidationError(("/: audit root must be an object",))
        expected_canonical = canonicalize_mgt_import_audit(payload)
        expected_hash = "sha256:" + hashlib.sha256(
            expected_canonical.encode("utf-8")
        ).hexdigest()
        envelope_issues: list[str] = []
        if self.schema_version != payload["schema_version"]:
            envelope_issues.append("/schema_version: envelope value does not match payload")
        if self.status != payload["status"]:
            envelope_issues.append("/status: envelope value does not match payload")
        if self.canonical_json != expected_canonical:
            envelope_issues.append("/: canonical_json is not canonical")
        if self.content_hash != expected_hash:
            envelope_issues.append("/: content_hash does not match canonical_json")
        if envelope_issues:
            raise MGTImportAuditValidationError(tuple(envelope_issues))

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self.canonical_json)
        if not isinstance(payload, dict):  # pragma: no cover - constructor invariant
            raise TypeError("MGT import audit must decode to an object.")
        return payload


class MGTImportAuditValidationError(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        self.issues = issues
        summary = "; ".join(issues[:5])
        if len(issues) > 5:
            summary += f"; ... {len(issues) - 5} more issue(s)"
        super().__init__(summary or "MGT import audit validation failed.")


def load_mgt_model_ir_v2_audit_schema() -> dict[str, Any]:
    schema_resource = resources.files("structural_analysis.schemas").joinpath(
        "mgt_model_ir_v2_audit.schema.json"
    )
    with schema_resource.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    if not isinstance(schema, dict):  # pragma: no cover - packaged schema invariant
        raise TypeError("Packaged MGT import audit schema must be an object.")
    Draft202012Validator.check_schema(schema)
    return schema


def canonicalize_mgt_import_audit(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def validate_mgt_import_audit(payload: Any) -> tuple[str, ...]:
    validator = Draft202012Validator(load_mgt_model_ir_v2_audit_schema())
    schema_issues = tuple(
        sorted(
            f"{_json_pointer(error.absolute_path)}: {error.message}"
            for error in validator.iter_errors(payload)
        )
    )
    if schema_issues or not isinstance(payload, dict):
        return schema_issues
    return tuple(sorted(_cross_invariant_issues(payload)))


def make_mgt_import_audit(payload: dict[str, Any]) -> MGTImportAudit:
    issues = validate_mgt_import_audit(payload)
    if issues:
        raise MGTImportAuditValidationError(issues)
    canonical_json = canonicalize_mgt_import_audit(payload)
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return MGTImportAudit(
        schema_version=str(payload["schema_version"]),
        status=str(payload["status"]),
        canonical_json=canonical_json,
        content_hash=f"sha256:{digest}",
    )


def json_pointer_exists(payload: Any, pointer: str) -> bool:
    if pointer == "":
        return True
    if not pointer.startswith("/"):
        return False
    current = payload
    for encoded in pointer[1:].split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            try:
                index = int(token)
            except ValueError:
                return False
            if index < 0 or index >= len(current):
                return False
            current = current[index]
        elif isinstance(current, dict):
            if token not in current:
                return False
            current = current[token]
        else:
            return False
    return True


def _json_pointer(path: Any) -> str:
    tokens = [str(token).replace("~", "~0").replace("/", "~1") for token in path]
    return "/" + "/".join(tokens) if tokens else "/"


def _cross_invariant_issues(payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    mappings = payload["source_mappings"]
    counts = payload["classification_counts"]
    calculated = {key: 0 for key in counts}
    for index, mapping in enumerate(mappings):
        disposition = str(mapping["disposition"])
        if disposition in calculated:
            calculated[disposition] += 1
        if (
            payload["status"] == "ready"
            and
            mapping["source_ref"]["logical_row_index"] is not None
            and disposition in {"SUPPORTED_EXACT", "SUPPORTED_NORMALIZED"}
            and not mapping["target_refs"]
        ):
            issues.append(
                f"/source_mappings/{index}/target_refs: supported data row has no target"
            )
    if calculated != counts:
        issues.append(
            "/classification_counts: counts do not match source_mappings dispositions"
        )
    if sum(int(value) for value in counts.values()) != len(mappings):
        issues.append(
            "/classification_counts: total does not equal source_mappings length"
        )

    roundtrip = payload["roundtrip_audit"]
    source_hash = roundtrip["supported_source_semantic_hash"]
    reverse_hash = roundtrip["reverse_projection_semantic_hash"]
    equivalent = bool(roundtrip["semantic_equivalent"])
    hashes_equal = (
        source_hash is not None
        and reverse_hash is not None
        and source_hash == reverse_hash
    )
    if equivalent != hashes_equal:
        issues.append(
            "/roundtrip_audit/semantic_equivalent: must equal semantic-hash equality"
        )

    if payload["status"] == "ready":
        model_ir = payload["model_ir"]
        if not (
            model_ir["content_hash"]
            and model_ir["contract_valid"]
            and model_ir["analysis_ready"]
        ):
            issues.append("/model_ir: ready audit requires a valid analysis-ready ModelIR")
        if any(row["severity"] == "error" for row in payload["diagnostics"]):
            issues.append("/diagnostics: ready audit cannot contain error diagnostics")
        if any(str(key).startswith("BLOCKED_") and int(value) for key, value in counts.items()):
            issues.append("/classification_counts: ready audit cannot contain blocked records")
        if not all(bool(value) for value in payload["capabilities"].values()):
            issues.append("/capabilities: ready audit requires every declared capability")
        if not equivalent:
            issues.append("/roundtrip_audit: ready audit requires semantic equivalence")
        if int(roundtrip["silent_loss_count"]) != 0:
            issues.append("/roundtrip_audit/silent_loss_count: ready audit requires zero")
        if int(roundtrip["target_pointer_error_count"]) != 0:
            issues.append(
                "/roundtrip_audit/target_pointer_error_count: ready audit requires zero"
            )
    return issues
