"""Public orchestration API for strict MGT to ModelIR v2 imports."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from structural_analysis.engine_v2 import (
    SolverModelBufferError,
    pack_solver_model_buffers,
)
from structural_analysis.io.midas.v2.audit import (
    MGT_MODEL_IR_V2_AUDIT_SCHEMA_VERSION,
    json_pointer_exists,
    make_mgt_import_audit,
)
from structural_analysis.io.midas.v2.classification import empty_classification_counts
from structural_analysis.io.midas.v2.lexer import lex_mgt, lex_mgt_bytes
from structural_analysis.io.midas.v2.mapping import map_mgt_document_to_model_ir
from structural_analysis.io.midas.v2.types import (
    MGTImportBlockedError,
    MGTImportResult,
)
from structural_analysis.io.midas.v2.writer import (
    MGTReverseProjectionError,
    model_ir_solver_semantic_hash,
    write_canonical_mgt_v2,
)
from structural_analysis.model_ir import (
    MODEL_IR_V2_SCHEMA_VERSION,
    ModelIRDocument,
    ModelIRValidationError,
    parse_model_ir_v2,
    validate_model_ir_v2,
)


def import_mgt_v2(
    path: str | Path,
    *,
    require_ready: bool = False,
) -> MGTImportResult:
    """Import a path and always return an audit unless I/O or UTF-8 decoding fails."""

    source_path = Path(path)
    source_document = lex_mgt(source_path)
    outcome = map_mgt_document_to_model_ir(source_document)
    cards = deepcopy(list(outcome.cards))
    source_mappings = deepcopy(list(outcome.source_mappings))
    diagnostics = deepcopy(list(outcome.diagnostics))

    model: ModelIRDocument | None = None
    model_contract_valid = False
    model_analysis_ready = False
    model_content_hash: str | None = None
    if outcome.payload is not None:
        report = validate_model_ir_v2(outcome.payload)
        model_contract_valid = report.contract_valid
        model_analysis_ready = report.analysis_ready
        model_content_hash = report.content_hash
        if report.contract_valid:
            try:
                model = parse_model_ir_v2(
                    outcome.payload, require_analysis_ready=False
                )
            except ModelIRValidationError as exc:  # pragma: no cover - report parity
                _append_diagnostic(
                    diagnostics,
                    "MODEL_IR_ENVELOPE_REJECTED",
                    str(exc),
                )
        else:
            for issue in report.issues:
                _append_diagnostic(
                    diagnostics,
                    f"MODEL_IR_{issue.code.upper()}",
                    f"{issue.path}: {issue.message}",
                )

    target_pointer_error_count = _target_pointer_error_count(
        outcome.payload, source_mappings
    )
    if target_pointer_error_count:
        _append_diagnostic(
            diagnostics,
            "MGT_AUDIT_TARGET_POINTER_INVALID",
            f"{target_pointer_error_count} audit target pointer(s) are invalid.",
        )

    expected_records = sum(
        (1 if block.header is not None else 0) + len(block.rows)
        for block in source_document.blocks
    )
    mapping_ids = [str(row["source_record_id"]) for row in source_mappings]
    silent_loss_count = abs(expected_records - len(source_mappings)) + (
        len(mapping_ids) - len(set(mapping_ids))
    )
    if silent_loss_count:
        _append_diagnostic(
            diagnostics,
            "MGT_AUDIT_SILENT_LOSS",
            f"Source-record accounting mismatch: {silent_loss_count}.",
        )

    solver_buffers_packable = False
    if model is not None and model.analysis_ready:
        try:
            for pattern in model.to_dict()["load_patterns"]:
                pack_solver_model_buffers(
                    model, load_pattern_id=str(pattern["id"])
                )
        except SolverModelBufferError as exc:
            _append_diagnostic(
                diagnostics,
                "MGT_SOLVER_BUFFER_PREFLIGHT_FAILED",
                str(exc),
            )
        else:
            solver_buffers_packable = True

    canonical_mgt: str | None = None
    source_semantic_hash: str | None = None
    reverse_semantic_hash: str | None = None
    semantic_equivalent = False
    if (
        model is not None
        and model.analysis_ready
        and solver_buffers_packable
        and target_pointer_error_count == 0
        and silent_loss_count == 0
    ):
        try:
            source_semantic_hash = model_ir_solver_semantic_hash(model)
            canonical_mgt = write_canonical_mgt_v2(model)
            reverse_source = lex_mgt_bytes(
                canonical_mgt.encode("utf-8"),
                source_name=f"roundtrip:{source_document.source.source_name}",
            )
            reverse_outcome = map_mgt_document_to_model_ir(reverse_source)
            if reverse_outcome.payload is None or reverse_outcome.fatal_syntax:
                raise MGTReverseProjectionError(
                    "MGT_REVERSE_REIMPORT_BLOCKED",
                    "/",
                    "Canonical MGT did not re-import through the strict grammar.",
                )
            reverse_model = parse_model_ir_v2(
                reverse_outcome.payload, require_analysis_ready=True
            )
            reverse_semantic_hash = model_ir_solver_semantic_hash(reverse_model)
            semantic_equivalent = source_semantic_hash == reverse_semantic_hash
            if not semantic_equivalent:
                raise MGTReverseProjectionError(
                    "MGT_REVERSE_SEMANTIC_HASH_MISMATCH",
                    "/",
                    "Canonical MGT re-import changed solver-authoritative semantics.",
                )
        except (MGTReverseProjectionError, ModelIRValidationError) as exc:
            canonical_mgt = None
            _append_diagnostic(
                diagnostics,
                "MGT_SEMANTIC_ROUNDTRIP_FAILED",
                str(exc),
            )

    classification_counts = empty_classification_counts()
    for mapping in source_mappings:
        classification_counts[str(mapping["disposition"])] += 1

    blocked_records = any(
        str(row["disposition"]).startswith("BLOCKED_")
        for row in source_mappings
    )
    error_diagnostics = any(row["severity"] == "error" for row in diagnostics)
    linear_static_ready = bool(
        model is not None
        and model.analysis_ready
        and not outcome.fatal_syntax
        and not blocked_records
    )
    supported_subset_roundtrip_ready = bool(
        semantic_equivalent
        and canonical_mgt is not None
        and target_pointer_error_count == 0
        and silent_loss_count == 0
    )
    status = (
        "ready"
        if linear_static_ready
        and solver_buffers_packable
        and supported_subset_roundtrip_ready
        and not error_diagnostics
        else "blocked"
    )

    audit_payload: dict[str, Any] = {
        "schema_version": MGT_MODEL_IR_V2_AUDIT_SCHEMA_VERSION,
        "source": {
            "ref": source_document.source.source_name,
            "sha256": "sha256:" + source_document.source.sha256,
            "byte_count": source_document.source.byte_count,
            "physical_line_count": source_document.source.physical_line_count,
            "encoding": source_document.source.encoding,
            "has_utf8_bom": source_document.source.has_utf8_bom,
            "newline_style": source_document.source.newline_style.name,
        },
        "adapter": {
            "adapter_id": "structural_analysis.io.midas.v2",
            "adapter_version": "1",
            "subset_contract": "midas_mgt_phase0_linear_frame.v1",
        },
        "status": status,
        "model_ir": {
            "schema_version": MODEL_IR_V2_SCHEMA_VERSION,
            "content_hash": model_content_hash,
            "contract_valid": model_contract_valid,
            "analysis_ready": model_analysis_ready,
        },
        "cards": cards,
        "source_mappings": source_mappings,
        "reference_audit": {
            "duplicate_ids": list(outcome.duplicate_ids),
            "dangling_references": list(outcome.dangling_references),
        },
        "roundtrip_audit": {
            "supported_source_semantic_hash": source_semantic_hash,
            "reverse_projection_semantic_hash": reverse_semantic_hash,
            "semantic_equivalent": semantic_equivalent,
            "silent_loss_count": silent_loss_count,
            "target_pointer_error_count": target_pointer_error_count,
        },
        "capabilities": {
            "linear_static_ready": linear_static_ready,
            "solver_buffers_packable": solver_buffers_packable,
            "supported_subset_roundtrip_ready": supported_subset_roundtrip_ready,
        },
        "diagnostics": diagnostics,
        "classification_counts": classification_counts,
        "claim_boundary": (
            "phase0_supported_subset_import_audit_not_full_midas_interoperability"
        ),
    }
    audit = make_mgt_import_audit(audit_payload)
    result = MGTImportResult(
        source_document=source_document,
        model_ir=model,
        audit=audit,
        canonical_mgt=canonical_mgt,
    )
    if require_ready and not result.ready:
        raise MGTImportBlockedError(result)
    return result


def _target_pointer_error_count(
    payload: dict[str, Any] | None,
    mappings: list[dict[str, Any]],
) -> int:
    if payload is None:
        return sum(len(row["target_refs"]) for row in mappings)
    return sum(
        1
        for mapping in mappings
        for target in mapping["target_refs"]
        if not json_pointer_exists(payload, str(target["json_pointer"]))
    )


def _append_diagnostic(
    diagnostics: list[dict[str, Any]],
    code: str,
    message: str,
) -> None:
    diagnostics.append(
        {
            "severity": "error",
            "code": code,
            "message": message,
            "line_start": None,
            "line_end": None,
        }
    )
