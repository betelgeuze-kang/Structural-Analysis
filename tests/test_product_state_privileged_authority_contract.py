"""Keep hosted replay's isolated authority guard fail-closed and source-aligned."""

from __future__ import annotations

import ast
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import textwrap
import unicodedata

import pytest

ROOT = Path(__file__).resolve().parents[1]
BINDINGS = (
    "same_operator_execution_binding",
    "stored_same_operator_execution_binding",
    "same_operator_supplemental_execution_binding",
    "stored_same_operator_supplemental_execution_binding",
)
METADATA = {
    "repository": "owner/repository",
    "family_attestation_count": 5,
    "same_operator_github_hosted_execution": True,
    "sigstore_attestations_reverified": True,
    "runtime_asset_metadata_sealed": True,
    "runtime_byte_lock_complete": True,
    "producer_signing_privilege_separated": True,
}
CONTEXTS = (
    ("product-state-provenance-bundle.v1", ("contracts", "post_main_overlay")),
    ("post-main-evidence-overlay.v1", ("generated_artifact_dag",)),
)


def _guard():
    workflow = (ROOT / ".github/workflows/product-state-current.yml").read_text()
    a = workflow.index("          def fail(reason):")
    b = workflow.index("          def validate_extra(extra):", a)
    source = textwrap.dedent(workflow[a:b])
    assert all(isinstance(node, ast.FunctionDef) for node in ast.parse(source).body)
    ns = {
        "base64": base64,
        "hashlib": hashlib,
        "json": json,
        "math": math,
        "re": re,
        "unicodedata": unicodedata,
    }
    exec(compile(source, "privileged-authority-helpers", "exec"), ns)
    ns["authority_policy"] = ns["load_authority_policy"](
        (ROOT / "canonical/nonpromotion-authority-key-policy.v1.json").read_bytes()
    )
    return ns["reject_promoted_authority"]


def _document(schema, pointer, key="release_leaf_contract_pass", value=True):
    result = {"schema_version": schema}
    target = result
    for part in pointer:
        target[part] = {}
        target = target[part]
    target[key] = value
    return result


@pytest.mark.parametrize("binding", BINDINGS)
def test_exact_execution_fact_paths(binding):
    _guard()(
        {
            "bounded_planar_external_vv": {
                binding: {"actual_external_solver_execution": True}
            }
        }
    )


@pytest.mark.parametrize("binding", BINDINGS[2:])
def test_exact_hosted_metadata_paths(binding):
    _guard()({"bounded_planar_external_vv": {binding: METADATA}})


@pytest.mark.parametrize("key", METADATA)
@pytest.mark.parametrize("binding", BINDINGS[2:])
def test_hosted_metadata_types_reject_boolean_as_count_and_wrong_scalars(key, binding):
    wrong = {
        "repository": ["", True, 1],
        "family_attestation_count": [True, -1, 9007199254740992, 1.0, "1"],
    }.get(key, [1, "true", {}, None])
    for value in wrong:
        with pytest.raises(SystemExit, match="supplemental_metadata_shape_invalid"):
            _guard()({"bounded_planar_external_vv": {binding: {key: value}}})


@pytest.mark.parametrize("binding", BINDINGS[:2] + ("future_binding",))
@pytest.mark.parametrize("key", METADATA)
def test_metadata_cannot_move_outside_supplemental_bindings(binding, key):
    with pytest.raises(SystemExit):
        _guard()({"bounded_planar_external_vv": {binding: {key: METADATA[key]}}})


@pytest.mark.parametrize("schema,pointer", CONTEXTS)
def test_leaf_fact_requires_explicit_validated_document_context(schema, pointer):
    payload = _document(schema, pointer)
    _guard()(payload, document_schema=schema)
    with pytest.raises(SystemExit, match="promoted_authority"):
        _guard()(payload)
    with pytest.raises(SystemExit, match="authority_document_schema_invalid"):
        _guard()(payload, document_schema="wrong")


@pytest.mark.parametrize("schema,pointer", CONTEXTS)
@pytest.mark.parametrize("value", [False, None, 1, 0, "true", {}, []])
def test_leaf_fact_remains_const_true(schema, pointer, value):
    with pytest.raises(SystemExit, match="release_leaf_contract_fact_invalid"):
        _guard()(_document(schema, pointer, value=value), document_schema=schema)


@pytest.mark.parametrize("schema,pointer", CONTEXTS)
@pytest.mark.parametrize(
    "key",
    [
        "releaseLeafContractPass",
        "release-leaf-contract-pass",
        "release_leaf_contract_pass_extra",
    ],
)
def test_leaf_fact_aliases_are_not_exempt(schema, pointer, key):
    with pytest.raises(SystemExit, match="promoted_authority"):
        _guard()(_document(schema, pointer, key=key), document_schema=schema)


@pytest.mark.parametrize("schema,pointer", CONTEXTS)
def test_leaf_fact_rejects_nested_list_and_other_context_transplants(schema, pointer):
    payload = _document(schema, pointer)
    for changed in (
        {"schema_version": schema, "nested": payload},
        {"schema_version": schema, pointer[0]: [payload[pointer[0]]]},
        _document(schema, ("future",) + pointer),
        _document(schema, CONTEXTS[1 if schema == CONTEXTS[0][0] else 0][1]),
    ):
        with pytest.raises(SystemExit, match="promoted_authority"):
            _guard()(changed, document_schema=schema)


@pytest.mark.parametrize("schema,pointer", CONTEXTS)
@pytest.mark.parametrize(
    "key",
    [
        "release_authority",
        "release_readiness",
        "scientific_authority",
        "design_authority",
        "independent_operator_attested",
        "product_legal_license_approval",
        "verification_level_2",
        "commercial_equivalence",
    ],
)
def test_document_context_never_allows_promotion(schema, pointer, key):
    payload = _document(schema, pointer)
    target = payload
    for part in pointer:
        target = target[part]
    target[key] = True
    with pytest.raises(SystemExit, match="promoted_authority"):
        _guard()(payload, document_schema=schema)


@pytest.mark.parametrize("binding", BINDINGS)
def test_execution_fact_cannot_be_aliased_or_transplanted(binding):
    for value in (
        {
            "bounded_planar_external_vv": {
                binding: {"future": {"actual_external_solver_execution": True}}
            }
        },
        {
            "bounded_planar_external_vv": {
                binding: {"actualExternalSolverExecution": True}
            }
        },
        {"future": {"actual_external_solver_execution": True}},
    ):
        with pytest.raises(SystemExit):
            _guard()(value)


def test_only_bundle_and_overlay_call_sites_select_context():
    workflow = (ROOT / ".github/workflows/product-state-current.yml").read_text()
    assert (
        'reject_promoted_authority(provenance, document_schema="product-state-provenance-bundle.v1")'
        in workflow
    )
    assert (
        'reject_promoted_authority(overlay, document_schema="post-main-evidence-overlay.v1")'
        in workflow
    )
    assert "reject_promoted_authority(product)" in workflow
    assert "reject_promoted_authority(receipt)" in workflow


@pytest.mark.parametrize("schema,pointer", CONTEXTS)
def test_leaf_fact_rejects_ancestor_aliases(schema, pointer):
    aliased = tuple("".join(part.title().split("_")) for part in pointer)
    with pytest.raises(SystemExit, match="promoted_authority"):
        _guard()(_document(schema, aliased), document_schema=schema)


def test_final_replay_preserves_candidate_bytes_and_uses_full_source_schemas():
    workflow = (ROOT / ".github/workflows/product-state-current.yml").read_text()
    assert workflow.count("def reject_promoted_authority(") == 1
    assert "jsonschema.Draft202012Validator(schema).validate(payload)" in workflow
    assert (
        'archive_files.get(name) != raw: fail(f"final_candidate_seal_row_bytes_invalid:{name}")'
        in workflow
    )
    assert (
        'if any(archive_files.get(name) != raw for name, raw in signed_files.items()): fail("final_artifact_replaced_signed_member")'
        in workflow
    )
    assert "gh attestation verify" in workflow
