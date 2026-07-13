from __future__ import annotations

from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator

from structural_analysis.io.midas.v2.audit import (
    MGTImportAudit,
    MGTImportAuditValidationError,
    json_pointer_exists,
    load_mgt_model_ir_v2_audit_schema,
    make_mgt_import_audit,
    validate_mgt_import_audit,
)


def _payload() -> dict:
    empty_counts = {
        "SUPPORTED_EXACT": 0,
        "SUPPORTED_NORMALIZED": 1,
        "PRESERVED_NONANALYTIC": 0,
        "BLOCKED_UNSUPPORTED": 0,
        "BLOCKED_INVALID_SYNTAX": 0,
        "BLOCKED_DUPLICATE_ID": 0,
        "BLOCKED_DANGLING_REFERENCE": 0,
        "BLOCKED_CONTEXT_MISSING": 0,
    }
    return {
        "schema_version": "structural-analysis-mgt-model-ir-v2-audit.v1",
        "source": {
            "ref": "fixture.mgt",
            "sha256": "sha256:" + "0" * 64,
            "byte_count": 10,
            "physical_line_count": 1,
            "encoding": "utf-8",
            "has_utf8_bom": False,
            "newline_style": "LF",
        },
        "adapter": {
            "adapter_id": "structural_analysis.io.midas.v2",
            "adapter_version": "1",
            "subset_contract": "midas_mgt_phase0_linear_frame.v1",
        },
        "status": "ready",
        "model_ir": {
            "schema_version": "structural-analysis-model-ir.v2",
            "content_hash": "sha256:" + "1" * 64,
            "contract_valid": True,
            "analysis_ready": True,
        },
        "cards": [
            {
                "name": "NODE",
                "occurrence_index": 1,
                "header_line": 1,
                "row_count": 0,
                "disposition": "SUPPORTED_NORMALIZED",
                "active_load_case": None,
                "reason_codes": [],
            }
        ],
        "source_mappings": [
            {
                "source_record_id": "MGT:NODE:1:HEADER",
                "source_ref": {
                    "section": "NODE",
                    "block_occurrence": 1,
                    "header_line": 1,
                    "line_start": 1,
                    "line_end": 1,
                    "logical_row_index": None,
                    "raw_sha256": "sha256:" + "3" * 64,
                },
                "disposition": "SUPPORTED_NORMALIZED",
                "target_refs": [],
                "transformations": [],
                "reason_codes": [],
            }
        ],
        "reference_audit": {"duplicate_ids": [], "dangling_references": []},
        "roundtrip_audit": {
            "supported_source_semantic_hash": "sha256:" + "2" * 64,
            "reverse_projection_semantic_hash": "sha256:" + "2" * 64,
            "semantic_equivalent": True,
            "silent_loss_count": 0,
            "target_pointer_error_count": 0,
        },
        "capabilities": {
            "linear_static_ready": True,
            "solver_buffers_packable": True,
            "supported_subset_roundtrip_ready": True,
        },
        "diagnostics": [],
        "classification_counts": empty_counts,
        "claim_boundary": (
            "phase0_supported_subset_import_audit_not_full_midas_interoperability"
        ),
    }


def test_audit_schema_and_immutable_canonical_envelope() -> None:
    schema = load_mgt_model_ir_v2_audit_schema()
    Draft202012Validator.check_schema(schema)

    audit = make_mgt_import_audit(_payload())
    second = make_mgt_import_audit(deepcopy(_payload()))

    assert audit.status == "ready"
    assert audit.content_hash == second.content_hash
    assert audit.canonical_json == second.canonical_json
    assert audit.to_dict() == _payload()


def test_audit_unknown_fields_and_bad_hashes_fail_closed() -> None:
    payload = _payload()
    payload["silent_claim"] = True
    assert validate_mgt_import_audit(payload)
    with pytest.raises(MGTImportAuditValidationError):
        make_mgt_import_audit(payload)

    payload = _payload()
    payload["source"]["sha256"] = "not-a-hash"
    assert validate_mgt_import_audit(payload)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["model_ir"].update(
            {"content_hash": None, "contract_valid": False, "analysis_ready": False}
        ),
        lambda payload: payload["roundtrip_audit"].update(
            {"reverse_projection_semantic_hash": "sha256:" + "4" * 64}
        ),
        lambda payload: payload["diagnostics"].append(
            {
                "severity": "error",
                "code": "BLOCKED",
                "message": "blocked fixture",
                "line_start": 1,
                "line_end": 1,
            }
        ),
        lambda payload: payload["capabilities"].update(
            {"solver_buffers_packable": False}
        ),
        lambda payload: payload["classification_counts"].update(
            {"SUPPORTED_NORMALIZED": 0, "BLOCKED_UNSUPPORTED": 1}
        ),
    ],
)
def test_ready_audit_cross_invariants_reject_contradictory_receipts(mutate) -> None:
    payload = _payload()
    mutate(payload)

    assert validate_mgt_import_audit(payload)
    with pytest.raises(MGTImportAuditValidationError):
        make_mgt_import_audit(payload)


def test_json_pointer_resolution_is_strict_and_unescapes_tokens() -> None:
    payload = {"nodes": [{"id": "N:1"}], "a/b": {"~key": 3}}

    assert json_pointer_exists(payload, "/nodes/0/id") is True
    assert json_pointer_exists(payload, "/a~1b/~0key") is True
    assert json_pointer_exists(payload, "/nodes/1") is False
    assert json_pointer_exists(payload, "nodes/0") is False


def test_public_audit_envelope_rejects_forged_hash_or_noncanonical_json() -> None:
    valid = make_mgt_import_audit(_payload())

    with pytest.raises(MGTImportAuditValidationError):
        MGTImportAudit(
            schema_version=valid.schema_version,
            status=valid.status,
            canonical_json=valid.canonical_json,
            content_hash="sha256:" + "f" * 64,
        )
    with pytest.raises(MGTImportAuditValidationError):
        MGTImportAudit(
            schema_version=valid.schema_version,
            status=valid.status,
            canonical_json="{\n" + valid.canonical_json[1:],
            content_hash=valid.content_hash,
        )
