"""File loader for validated Engine v2 ModelIR documents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from structural_analysis.model_ir.types import ModelIRDocument
from structural_analysis.model_ir.validation import (
    ModelIRValidationError,
    canonicalize_model_ir_v2,
    load_json_object_strict,
    validate_model_ir_v2,
)


def load_model_ir_v2(
    path: str | Path,
    *,
    require_analysis_ready: bool = True,
) -> ModelIRDocument:
    model_path = Path(path)
    payload = load_json_object_strict(model_path)
    return parse_model_ir_v2(payload, require_analysis_ready=require_analysis_ready)


def parse_model_ir_v2(
    payload: Any,
    *,
    require_analysis_ready: bool = True,
) -> ModelIRDocument:
    """Validate an in-memory payload and freeze it as canonical ModelIR JSON."""

    report = validate_model_ir_v2(payload)
    if not report.contract_valid or (
        require_analysis_ready and not report.analysis_ready
    ):
        raise ModelIRValidationError(report)
    if not isinstance(payload, dict):  # pragma: no cover - report invariant
        raise TypeError("ModelIR v2 root must be an object.")
    if (
        report.content_hash is None
        or report.semantic_hash is None
        or report.provenance_hash is None
    ):  # pragma: no cover - report invariant
        raise ModelIRValidationError(report)
    return ModelIRDocument(
        schema_version=str(payload["schema_version"]),
        model_id=str(payload["model_id"]),
        capability_profile=str(payload["capability_profile"]),
        canonical_json=canonicalize_model_ir_v2(payload),
        content_hash=report.content_hash,
        semantic_hash=report.semantic_hash,
        provenance_hash=report.provenance_hash,
        analysis_ready=report.analysis_ready,
        blocking_feature_ids=report.blocking_feature_ids,
        derived_blocking_feature_ids=report.derived_blocking_feature_ids,
    )
