"""Source-bound public planar integration; not independent external V&V."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.sparse import eye

from structural_analysis.adapters.bounded_planar_model_ir import (
    adapt_bounded_planar_model_ir_v2,
)
from structural_analysis.api import nonlinear_frame as nonlinear_frame_api
from structural_analysis.api import planar_frame as planar_frame_api
from structural_analysis.api.nonlinear_frame import validate_nonlinear_frame_manifest
from structural_analysis.api.planar_frame import (
    PlanarFrameConfig,
    analyze_planar_frame,
    validate_planar_frame_result,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_checkpoint_chain_io import (
    dump_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes,
    load_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes,
    make_stateful_corotational_fiber_frame2d_checkpoint_chain,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.model_ir import parse_model_ir_v2
from structural_analysis.solvers.nonlinear import sparse_factorization
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_MATRIX_BACKEND,
    VECTOR_SPARSE_MATRIX_BACKEND,
)
from structural_analysis.solvers.nonlinear.sparse_factorization import (
    SparseFactorizationError,
    SparseFactorizationPolicy,
    factorize_and_solve_sparse,
)


FIXTURE = Path(__file__).resolve().parents[1] / "examples/planar_frame_rc_portal.json"
BACKENDS = (VECTOR_MATRIX_BACKEND, VECTOR_SPARSE_MATRIX_BACKEND)
SI_ROWS = (
    "node_displacements",
    "support_reactions",
    "member_end_forces",
    "section_results",
    "fiber_results",
)


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _bind_generated_source(payload: dict) -> dict:
    # The generated recipe is the complete normalized model excluding provenance.
    payload["provenance"]["source_sha256"] = canonical_hash(
        {key: value for key, value in payload.items() if key != "provenance"}
    )
    return payload


def _assert_rows_close(left, right) -> None:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        assert left.keys() == right.keys()
        for key in left:
            _assert_rows_close(left[key], right[key])
    elif isinstance(left, (tuple, list)) and isinstance(right, (tuple, list)):
        assert len(left) == len(right)
        for first, second in zip(left, right, strict=True):
            _assert_rows_close(first, second)
    elif type(left) in (int, float) and type(right) in (int, float):
        assert np.isfinite(left) and np.isfinite(right)
        np.testing.assert_allclose(left, right, rtol=1.0e-9, atol=1.0e-9)
    else:
        assert left == right


@pytest.fixture(scope="module")
def portal_results():
    payload = _payload()
    assert payload == _bind_generated_source(deepcopy(payload))
    document = parse_model_ir_v2(payload, require_analysis_ready=True)
    results = {}
    for backend in BACKENDS:
        config = PlanarFrameConfig(load_steps=2, matrix_backend=backend)
        result = analyze_planar_frame(document, config)
        assert result.status == "converged", result.to_dict()
        results[backend] = (document, config, result)
    return results


def test_public_portal_dense_sparse_full_si_parity_and_source_binding(
    portal_results,
) -> None:
    dense = portal_results[VECTOR_MATRIX_BACKEND][2].to_dict()["result_ir"]
    sparse = portal_results[VECTOR_SPARSE_MATRIX_BACKEND][2].to_dict()["result_ir"]
    for backend, (document, _, result) in portal_results.items():
        report = validate_planar_frame_result(result)
        assert report.artifact_contract_pass and report.execution_contract_pass
        assert report.numerical_result_authority and report.engineering_result_authority
        assert result.public is True and result.release_eligible is False
        assert result.authority["external_vv"] == "not_attached"
        assert result.authority["engineering_design"] == "not_authoritative"
        source = result.to_dict()["result_ir"]
        validate_nonlinear_frame_manifest(source)
        assert source["profile"] == "corotational_connected_frame2d.v1"
        assert source["configuration"]["matrix_backend"] == backend
        bindings = source["contract_bindings"]
        adapter = bindings["source_model_ir_adapter"]
        assert adapter["model_ir_content_hash"] == document.content_hash
        assert adapter["model_ir_semantic_hash"] == document.semantic_hash
        assert adapter["model_ir_provenance_hash"] == document.provenance_hash
        assert adapter["canonical_model_checksum"] == source["canonical_model_checksum"]
        assert bindings["bounded_planar_execution_plan"]["model_ir_content_hash"] == (
            document.content_hash
        )
        assert (
            bindings["engineering_result_hash"]
            == (source["engineering_result_ir"]["engineering_result_hash"])
        )
        assert source["metrics"]["exact_engineering_recovery"] is True
        assert source["metrics"]["exact_checkpoint_chain_replay"] is True
        assert source["metrics"]["fallback_count"] == 0
        assert source["metrics"]["regularization_count"] == 0
        assert source["metrics"]["external_level2_attached"] is False
        assert len(source["node_displacements"]) == 4
        assert len(source["member_end_forces"]) == 3
        reactions = source["support_reactions"]
        assert {(row["node_id"], row["dof"]) for row in reactions} == {
            (node, dof) for node in ("N1", "N2") for dof in ("UX", "UY", "RZ")
        }
        for dof, total in (("UX", -20_000.0), ("UY", 50_000.0)):
            assert sum(row["value_si"] for row in reactions if row["dof"] == dof) == (
                pytest.approx(total, rel=1.0e-9, abs=1.0e-6)
            )
        for field in SI_ROWS:
            assert source[field]
    for field in SI_ROWS:
        _assert_rows_close(dense[field], sparse[field])
    assert dense["metrics"]["native_sparse_assembly_used"] is False
    metrics = sparse["metrics"]
    assert metrics["native_sparse_assembly_used"] is True
    assert metrics["sparse_factorization_diagnostics_passed"] is True
    assert metrics["sparse_factorization_count"] > 0
    assert (
        len(metrics["sparse_factorization_diagnostic_hashes"])
        == (metrics["sparse_factorization_count"])
    )
    assert metrics["sparse_factorization_max_condition_number_1"] <= 1.0e12
    assert metrics["sparse_factorization_max_backward_error"] <= 1.0e-12


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("prefix_steps", (1, 2), ids=("prefix", "terminal"))
def test_public_portal_restart_preserves_backend_results_and_checkpoint_bytes(
    portal_results,
    backend: str,
    prefix_steps: int,
) -> None:
    document, config, first = portal_results[backend]
    checkpoint = first.checkpoint_artifact()
    if prefix_steps < config.load_steps:
        adapter = adapt_bounded_planar_model_ir_v2(document)
        # Repackage a real accepted prefix, never synthesize solver state.
        compiled = nonlinear_frame_api._compile_portal(
            adapter.canonical_model,
            general_profile=True,
            source_model_ir_adapter=adapter,
        )
        chain = load_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes(
            checkpoint,
            compiled.problem,
        )
        prefix = make_stateful_corotational_fiber_frame2d_checkpoint_chain(
            compiled.problem,
            chain.checkpoints[: prefix_steps + 1],
        )
        checkpoint = dump_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes(
            compiled.problem,
            prefix,
        )
    resumed = analyze_planar_frame(
        document,
        config,
        restart_checkpoint_chain=checkpoint,
    )
    assert validate_planar_frame_result(resumed).engineering_result_authority is True
    assert resumed.checkpoint_artifact() == first.checkpoint_artifact()
    source = resumed.to_dict()["result_ir"]
    original = first.to_dict()["result_ir"]
    assert source["configuration"]["matrix_backend"] == backend
    assert source["metrics"]["replayed_prefix_step_count"] == prefix_steps
    assert source["metrics"]["newly_solved_step_count"] == 2 - prefix_steps
    assert source["contract_bindings"] == original["contract_bindings"]
    assert source["engineering_result_ir"] == original["engineering_result_ir"]
    for field in SI_ROWS:
        assert source[field] == original[field]


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("change", ("width_m", "top_bar_count"))
def test_public_portal_rejects_other_physical_candidate_checkpoint(
    portal_results,
    backend: str,
    change: str,
) -> None:
    document, config, baseline = portal_results[backend]
    payload = _payload()
    payload["sections"][0]["parameters"][change] = 0.45 if change == "width_m" else 3
    candidate = parse_model_ir_v2(
        _bind_generated_source(payload),
        require_analysis_ready=True,
    )
    assert candidate.content_hash != document.content_hash
    assert candidate.semantic_hash != document.semantic_hash
    rejected = analyze_planar_frame(
        candidate,
        config,
        restart_checkpoint_chain=baseline.checkpoint_artifact(),
    )
    _assert_no_result_authority(rejected)
    source = rejected.to_dict()["result_ir"]
    assert source["metrics"]["solver_executed"] is False
    assert source["input_checksum"] == candidate.content_hash
    assert (
        source["canonical_model_checksum"]
        != (baseline.result_ir["canonical_model_checksum"])
    )
    assert source["unsupported_features"][0]["path"] == "/restart_checkpoint_chain"


def _rehash_outer(result, **changes):
    tampered = replace(result, **changes)
    payload = tampered.to_dict()
    payload.pop("result_hash")
    return replace(tampered, result_hash=canonical_hash(payload))


@pytest.mark.parametrize(
    "tamper", ("incomplete", "inner_hash", "engineering_binding", "source_binding")
)
def test_public_wrapper_rejects_invalid_nested_result_after_outer_rehash(
    portal_results,
    tamper: str,
) -> None:
    original = portal_results[VECTOR_SPARSE_MATRIX_BACKEND][2]
    source = original.to_dict()["result_ir"]
    if tamper == "incomplete":
        source = {"profile": "corotational_connected_frame2d.v1", "contract_pass": True}
    elif tamper == "inner_hash":
        source["node_displacements"][3]["UX_m"] += 1.0
    else:
        if tamper == "engineering_binding":
            source["contract_bindings"]["engineering_result_hash"] = (
                "sha256:" + "0" * 64
            )
        else:
            source["input_checksum"] = "sha256:" + "0" * 64
        # Even a correctly rehashed unified envelope cannot bypass its nested bindings.
        source["result_hash"] = canonical_hash(
            {key: value for key, value in source.items() if key != "result_hash"}
        )
    tampered = _rehash_outer(original, result_ir=source)
    with pytest.raises(ValueError):
        validate_planar_frame_result(tampered)


@pytest.mark.parametrize("status", ("converged", "not_run"))
@pytest.mark.parametrize(
    ("axis", "value"),
    (
        ("external_vv", "independent_level2"),
        ("engineering_design", "authoritative"),
        ("release_readiness", "authoritative"),
        ("commercial_release", "not_authoritative"),
        ("external_vv", None),
    ),
)
def test_public_wrapper_rejects_rehashed_authority_changes(
    portal_results,
    status: str,
    axis: str,
    value: str | None,
) -> None:
    document, _, original = portal_results[VECTOR_MATRIX_BACKEND]
    if status == "not_run":
        original = analyze_planar_frame(
            document, PlanarFrameConfig(control="arc_length")
        )
    authority = dict(original.authority)
    if value is None:
        authority.pop(axis)
    else:
        authority[axis] = value
    tampered = _rehash_outer(original, authority=authority)
    with pytest.raises(ValueError, match="authority differs from profile contract"):
        validate_planar_frame_result(tampered)


@pytest.mark.parametrize("backend", BACKENDS)
def test_nested_validation_does_not_change_valid_result_manifest_or_hash(
    portal_results,
    backend: str,
    monkeypatch,
) -> None:
    document, config, validated = portal_results[backend]
    # The added detached validator is read-only: bypass just that new check and
    # compare an otherwise identical fresh public execution against the validated one.
    with monkeypatch.context() as context:
        context.setattr(
            planar_frame_api, "validate_nonlinear_frame_manifest", lambda source: source
        )
        without_new_check = analyze_planar_frame(document, config)
    assert without_new_check.to_dict() == validated.to_dict()
    assert without_new_check.result_hash == validated.result_hash
    assert without_new_check.checkpoint_artifact() == validated.checkpoint_artifact()
    before = deepcopy(validated.to_dict())
    assert validate_planar_frame_result(validated).engineering_result_authority is True
    assert validated.to_dict() == before


def _assert_no_result_authority(result) -> None:
    assert result.status == "not_converged" and result.converged is False
    report = validate_planar_frame_result(result)
    assert report.artifact_contract_pass and report.diagnostic_authority
    assert not report.numerical_result_authority
    assert not report.engineering_result_authority
    assert result.release_eligible is False
    source = result.to_dict()["result_ir"]
    assert source["engineering_result_ir"] is None
    assert source["checkpoint"]["available"] is False
    assert source["metrics"]["fallback_count"] == 0
    assert source["metrics"]["regularization_count"] == 0
    for field in SI_ROWS:
        assert source[field] == []
    with pytest.raises(ValueError, match="no checkpoint-chain artifact"):
        result.checkpoint_artifact()


def _subdivided_portal_payload() -> dict:
    payload = _payload()
    originals = list(payload["elements"])
    payload["elements"] = []
    coordinates = {
        row["id"]: np.array(row["coordinates_m"]) for row in payload["nodes"]
    }
    for original in originals:
        first, last = original["node_ids"]
        member_nodes = [first]
        for index in range(1, 29):
            node_id = f"{original['id']}-node-{index}"
            point = coordinates[first] + index / 29 * (
                coordinates[last] - coordinates[first]
            )
            payload["nodes"].append(
                {
                    "id": node_id,
                    "index": len(payload["nodes"]),
                    "coordinates_m": point.tolist(),
                    "source_id": f"generated:{node_id}",
                    "extensions": {},
                }
            )
            constraint = deepcopy(payload["constraints"][2])
            constraint.update(
                {
                    "id": f"inactive-{node_id}",
                    "index": len(payload["constraints"]),
                    "node_id": node_id,
                    "source_id": f"generated:inactive-{node_id}",
                }
            )
            payload["constraints"].append(constraint)
            member_nodes.append(node_id)
        member_nodes.append(last)
        for index, (node_i, node_j) in enumerate(zip(member_nodes, member_nodes[1:])):
            member = deepcopy(original)
            member.update(
                {
                    "id": f"{original['id']}-{index}",
                    "index": len(payload["elements"]),
                    "node_ids": [node_i, node_j],
                    "source_id": f"generated:{original['id']}-{index}",
                }
            )
            payload["elements"].append(member)
    return _bind_generated_source(payload)


def test_sparse_exact_condition_policy_accepts_256_and_rejects_257_equations() -> None:
    assert SparseFactorizationPolicy().maximum_exact_condition_equations == 256
    accepted = factorize_and_solve_sparse(eye(256, format="csr"), np.ones(256))
    assert accepted.diagnostic.contract_pass
    assert accepted.diagnostic.equation_count == 256
    np.testing.assert_array_equal(accepted.solution, np.ones(256))
    with pytest.raises(
        SparseFactorizationError, match="sparse_condition_diagnostic_scope_exceeded"
    ):
        factorize_and_solve_sparse(eye(257, format="csr"), np.ones(257))


def test_public_planar_sparse_scope_cap_fails_before_factorization(monkeypatch) -> None:
    payload = _subdivided_portal_payload()
    assert len(payload["nodes"]) == 88
    assert len(payload["elements"]) == 87
    # The source is within the public topology bounds but has 3*88-6=258 free DOFs.
    document = parse_model_ir_v2(payload, require_analysis_ready=True)

    def unexpected_factorization(*_args, **_kwargs):
        pytest.fail("out-of-scope public sparse input must not factor or fall back")

    monkeypatch.setattr(sparse_factorization, "splu", unexpected_factorization)
    monkeypatch.setattr(np.linalg, "solve", unexpected_factorization)
    result = analyze_planar_frame(
        document,
        PlanarFrameConfig(load_steps=2, matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND),
    )
    _assert_no_result_authority(result)
    source = result.to_dict()["result_ir"]
    assert source["metrics"]["solver_executed"] is True
    assert source["metrics"]["sparse_factorization_count"] == 0
    assert source["unsupported_features"][0]["path"] == "/solver"
    assert (
        "sparse_condition_diagnostic_scope_exceeded"
        in (source["unsupported_features"][0]["detail"])
    )
