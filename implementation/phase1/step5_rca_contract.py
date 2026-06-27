#!/usr/bin/env python3
"""Static Step5 RCA contract helper for mobile/web-only development.

This module mirrors ``step5_rca_summary.schema.json`` without running solver,
Rust/HIP, npm, Playwright, or CI. A later ``phase1_ci_gate.py`` pass can import
or inline these constants to make missing/invalid RCA detail reporting use the
same vocabulary as the mobile/static contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

STEP5_RCA_SCHEMA_ANCHOR = "implementation/phase1/step5_rca_summary.schema.json"
STEP5_RCA_TIMING_FIELD = "timing_breakdown_seconds"
STEP5_RCA_REQUIRED_TIMING_FIELDS = ("compute", "host_copy", "serialization")
STEP5_RCA_OPTIONAL_PROVENANCE_FIELDS = (
    "schema_version",
    "generated_at_utc",
    "run_id",
    "producer",
    "host_copy_share",
    "zero_copy_pass",
    "strict_probe_ref",
    "artifact_manifest",
)
PASS = "PASS"
ERR_MISSING_RCA_KEY = "ERR_MISSING_RCA_KEY"
ERR_INVALID_RCA_VALUE = "ERR_INVALID_RCA_VALUE"


@dataclass(frozen=True)
class Step5RcaValidation:
    contract_pass: bool
    reason_code: str
    missing_fields: tuple[str, ...] = field(default_factory=tuple)
    invalid_fields: tuple[str, ...] = field(default_factory=tuple)
    schema_anchor: str = STEP5_RCA_SCHEMA_ANCHOR

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_pass": self.contract_pass,
            "reason_code": self.reason_code,
            "missing_fields": list(self.missing_fields),
            "invalid_fields": list(self.invalid_fields),
            "schema_anchor": self.schema_anchor,
            "required_timing_fields": list(STEP5_RCA_REQUIRED_TIMING_FIELDS),
            "optional_provenance_fields": list(STEP5_RCA_OPTIONAL_PROVENANCE_FIELDS),
        }


def _finite_number(value: object) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def _finite_non_negative(value: object) -> bool:
    number = _finite_number(value)
    return bool(number is not None and number >= 0.0)


def _valid_host_copy_share(value: object) -> bool:
    number = _finite_number(value)
    return bool(number is not None and 0.0 <= number <= 1.0)


def validate_step5_rca_summary(payload: dict[str, Any] | object) -> Step5RcaValidation:
    if not isinstance(payload, dict) or STEP5_RCA_TIMING_FIELD not in payload:
        return Step5RcaValidation(False, ERR_MISSING_RCA_KEY, (STEP5_RCA_TIMING_FIELD,))
    timing = payload.get(STEP5_RCA_TIMING_FIELD)
    if not isinstance(timing, dict):
        return Step5RcaValidation(False, ERR_MISSING_RCA_KEY, (STEP5_RCA_TIMING_FIELD,))

    missing: list[str] = []
    invalid: list[str] = []
    for key in STEP5_RCA_REQUIRED_TIMING_FIELDS:
        field_path = f"{STEP5_RCA_TIMING_FIELD}.{key}"
        if key not in timing:
            missing.append(field_path)
        elif not _finite_non_negative(timing[key]):
            invalid.append(field_path)
    if "host_copy_share" in payload and not _valid_host_copy_share(payload.get("host_copy_share")):
        invalid.append("host_copy_share")
    if missing:
        return Step5RcaValidation(False, ERR_MISSING_RCA_KEY, tuple(missing), tuple(invalid))
    if invalid:
        return Step5RcaValidation(False, ERR_INVALID_RCA_VALUE, (), tuple(invalid))
    return Step5RcaValidation(True, PASS)
