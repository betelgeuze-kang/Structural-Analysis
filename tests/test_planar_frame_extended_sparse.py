"""Actual bounded public sparse integration, without independent external V&V."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
from time import perf_counter

import numpy as np
import pytest
from scipy.sparse import isspmatrix_csr

from structural_analysis.adapters.bounded_planar_model_ir import (
    adapt_bounded_planar_model_ir_v2,
)
from structural_analysis.api import nonlinear_frame as nonlinear_frame_api
from structural_analysis.api.nonlinear_frame import (
    COROTATIONAL_GENERAL_PROFILE,
    NonlinearFrameConfig,
    analyze_nonlinear_frame,
    validate_nonlinear_frame_manifest,
    validate_nonlinear_frame_result,
)
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
from structural_analysis.solvers.nonlinear import newton, sparse_factorization
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND,
    VECTOR_MATRIX_BACKEND,
    VECTOR_SPARSE_MATRIX_BACKEND,
    sparse_factorization_policy_for_backend,
)
from structural_analysis.solvers.nonlinear.sparse_factorization import (
    SparseFactorizationPolicy,
)
from tests.test_planar_frame_public_sparse_integration import (
    SI_ROWS,
    _assert_no_result_authority,
    _assert_rows_close,
    _rehash_outer,
    _subdivided_portal_payload,
)
from tests.test_unified_nonlinear_frame_api import _branching_payload, _model


def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _preserve_result(directory: Path, name: str, result, elapsed: float) -> None:
    report = result.to_dict()
    _write_json(directory / f"{name}-result.json", report)
    _write_json(
        directory / f"{name}-observation.json",
        {
            "status": result.status,
            "elapsed_seconds": elapsed,
            "timing_scope": "integration_test_including_public_validation",
            "isolated_performance_observation": False,
            "independent_external_vv": False,
        },
    )
    if result.converged:
        (directory / f"{name}-checkpoint.json").write_bytes(
            result.checkpoint_artifact()
        )
    print(
        f"{name}: status={result.status}, elapsed_seconds={elapsed:.3f}, "
        f"artifacts={directory}, "
        f"unsupported={report['result_ir']['unsupported_features']}",
        flush=True,
    )


@pytest.fixture(scope="module")
def artifact_directory() -> Path:
    return Path(tempfile.mkdtemp(prefix="structural-extended-sparse-"))


@pytest.fixture(scope="module")
def extended_case(artifact_directory):
    """The extended solve is the first probe and is shared by every assertion."""
    directory = artifact_directory
    payload = _subdivided_portal_payload()
    _write_json(directory / "model.json", payload)
    assert len(payload["nodes"]) == 88
    assert len(payload["elements"]) == 87
    document = parse_model_ir_v2(payload, require_analysis_ready=True)
    adapter = adapt_bounded_planar_model_ir_v2(document)
    compiled = nonlinear_frame_api._compile_portal(
        adapter.canonical_model,
        general_profile=True,
        source_model_ir_adapter=adapter,
    )
    assert len(compiled.problem.free_global_dofs) == 258
    config = PlanarFrameConfig(
        load_steps=2, matrix_backend=VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND
    )
    calls = []
    original_increment = newton._solve_vector_increment

    def observe_increment(jacobian, residual, *, matrix_backend):
        # Observe the original tangent before the increment helper can convert it.
        calls.append((matrix_backend, isspmatrix_csr(jacobian), jacobian.shape))
        return original_increment(jacobian, residual, matrix_backend=matrix_backend)

    print(f"extended 258-equation public probe starting: {directory}", flush=True)
    started = perf_counter()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(newton, "_solve_vector_increment", observe_increment)
        result = analyze_planar_frame(document, config)
    _preserve_result(directory, "extended", result, perf_counter() - started)
    assert result.status == "converged", result.to_dict()["result_ir"]
    return document, config, result, compiled, directory, calls


def test_extended_public_probe_has_strict_policy_native_csr_and_source_authority(
    extended_case,
) -> None:
    document, config, result, _, directory, calls = extended_case
    assert VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND == "scipy_sparse_splu_cpu_exact_1536"
    assert PlanarFrameConfig().matrix_backend == VECTOR_MATRIX_BACKEND
    assert config.residual_tolerance == 1.0e-10
    assert config.increment_tolerance_m == 1.0e-12
    policy = sparse_factorization_policy_for_backend(config.matrix_backend)
    assert policy == SparseFactorizationPolicy(maximum_exact_condition_equations=1536)
    assert policy.maximum_condition_number_1 == 1.0e12
    assert policy.minimum_normalized_absolute_pivot == 1.0e-14
    assert policy.maximum_backward_error == 1.0e-12
    assert policy.policy_hash != SparseFactorizationPolicy().policy_hash
    assert calls
    assert all(
        backend == config.matrix_backend and native and shape == (258, 258)
        for backend, native, shape in calls
    )
    report = validate_planar_frame_result(result)
    assert report.artifact_contract_pass and report.execution_contract_pass
    assert report.numerical_result_authority and report.engineering_result_authority
    assert result.public is True and result.release_eligible is False
    assert result.authority["external_vv"] == "not_attached"
    assert result.authority["engineering_design"] == "not_authoritative"
    source = result.to_dict()["result_ir"]
    validate_nonlinear_frame_manifest(source)
    assert source["configuration"]["matrix_backend"] == config.matrix_backend
    assert source["configuration"]["stiffness_storage"] == "scipy_sparse_csr"
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
    metrics = source["metrics"]
    for field in (
        "exact_engineering_recovery",
        "exact_checkpoint_chain_replay",
        "sparse_backend_used",
        "native_sparse_assembly_used",
        "sparse_factorization_diagnostics_passed",
    ):
        assert metrics[field] is True
    assert metrics["fallback_count"] == metrics["regularization_count"] == 0
    assert metrics["external_level2_attached"] is False
    assert metrics["sparse_factorization_count"] > 0
    assert (
        len(metrics["sparse_factorization_diagnostic_hashes"])
        == (metrics["sparse_factorization_count"])
    )
    assert metrics["sparse_factorization_policy_hash"] == policy.policy_hash
    assert 0 <= metrics["sparse_factorization_max_condition_number_1"] <= 1.0e12
    assert 1.0e-14 <= metrics["sparse_factorization_min_normalized_absolute_pivot"] <= 1
    assert 0 <= metrics["sparse_factorization_max_backward_error"] <= 1.0e-12
    assert len(source["node_displacements"]) == 88
    assert len(source["member_end_forces"]) == 87
    assert all(source[field] for field in SI_ROWS)
    assert (directory / "extended-checkpoint.json").read_bytes() == (
        result.checkpoint_artifact()
    )


def test_extended_public_all_si_rows_match_dense_reference(extended_case) -> None:
    document, config, sparse, _, directory, _ = extended_case
    dense_config = PlanarFrameConfig(load_steps=config.load_steps)
    started = perf_counter()
    dense = analyze_planar_frame(document, dense_config)
    _preserve_result(directory, "dense", dense, perf_counter() - started)
    assert dense.status == "converged", dense.to_dict()["result_ir"]
    assert validate_planar_frame_result(dense).engineering_result_authority
    dense_source = dense.to_dict()["result_ir"]
    sparse_source = sparse.to_dict()["result_ir"]
    assert dense_source["metrics"]["native_sparse_assembly_used"] is False
    assert (
        dense_source["canonical_model_checksum"]
        == (sparse_source["canonical_model_checksum"])
    )
    for field in SI_ROWS:
        _assert_rows_close(dense_source[field], sparse_source[field])


def test_extended_public_prefix_restart_preserves_physical_identity(
    extended_case,
) -> None:
    document, config, original, compiled, directory, _ = extended_case
    chain = load_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes(
        original.checkpoint_artifact(), compiled.problem
    )
    prefix = make_stateful_corotational_fiber_frame2d_checkpoint_chain(
        compiled.problem, chain.checkpoints[:2]
    )
    checkpoint = dump_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes(
        compiled.problem, prefix
    )
    (directory / "prefix-checkpoint.json").write_bytes(checkpoint)
    started = perf_counter()
    resumed = analyze_planar_frame(
        document, config, restart_checkpoint_chain=checkpoint
    )
    _preserve_result(directory, "resumed", resumed, perf_counter() - started)
    assert validate_planar_frame_result(resumed).engineering_result_authority
    assert resumed.checkpoint_artifact() == original.checkpoint_artifact()
    source = resumed.to_dict()["result_ir"]
    baseline = original.to_dict()["result_ir"]
    assert source["configuration"]["matrix_backend"] == config.matrix_backend
    assert source["metrics"]["replayed_prefix_step_count"] == 1
    assert source["metrics"]["newly_solved_step_count"] == 1
    assert source["contract_bindings"] == baseline["contract_bindings"]
    assert source["engineering_result_ir"] == baseline["engineering_result_ir"]
    for field in SI_ROWS:
        assert source[field] == baseline[field]


def test_extended_opt_in_does_not_change_legacy_256_equation_cap(
    extended_case, monkeypatch
) -> None:
    document, _, _, _, directory, _ = extended_case
    assert SparseFactorizationPolicy().maximum_exact_condition_equations == 256
    assert sparse_factorization_policy_for_backend(VECTOR_SPARSE_MATRIX_BACKEND) == (
        SparseFactorizationPolicy()
    )

    def unexpected_factorization(*_args, **_kwargs):
        pytest.fail("legacy cap must reject before factorization or dense fallback")

    monkeypatch.setattr(sparse_factorization, "splu", unexpected_factorization)
    monkeypatch.setattr(np.linalg, "solve", unexpected_factorization)
    started = perf_counter()
    result = analyze_planar_frame(
        document,
        PlanarFrameConfig(load_steps=2, matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND),
    )
    _preserve_result(directory, "legacy-blocked", result, perf_counter() - started)
    _assert_no_result_authority(result)
    source = result.to_dict()["result_ir"]
    assert source["metrics"]["sparse_factorization_count"] == 0
    assert (
        "sparse_condition_diagnostic_scope_exceeded"
        in (source["unsupported_features"][0]["detail"])
    )


@pytest.fixture(scope="module")
def prescribed_only_result(artifact_directory):
    payload = _branching_payload()
    payload["loads"] = []
    payload["supports"] = [
        {
            "node": row["id"],
            "dofs": ["UX", "UY", "RZ"],
            **({"prescribed_values": {"UX": 1.0e-4}} if row["id"] == "N6" else {}),
        }
        for row in payload["nodes"]
    ]

    def unexpected_increment(*_args, **_kwargs):
        pytest.fail("prescribed-only execution must not solve a Newton increment")

    model = _model(artifact_directory, payload, "extended-prescribed-only-model.json")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(newton, "_solve_vector_increment", unexpected_increment)
        result = analyze_nonlinear_frame(
            model,
            NonlinearFrameConfig(
                profile=COROTATIONAL_GENERAL_PROFILE,
                load_steps=2,
                matrix_backend=VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND,
            ),
        )
    _write_json(
        artifact_directory / "extended-prescribed-only-result.json", result.to_dict()
    )
    (artifact_directory / "extended-prescribed-only-checkpoint.json").write_bytes(
        result.checkpoint_artifact()
    )
    return result


def test_extended_prescribed_only_preserves_no_newton_contract(
    prescribed_only_result,
) -> None:
    result = prescribed_only_result
    assert validate_nonlinear_frame_result(result).contract_pass is True
    validate_nonlinear_frame_manifest(result.to_dict())
    assert result.metrics["solver_executed"] is False
    assert result.metrics["no_solve_contract_pass"] is True
    assert result.metrics["sparse_backend_used"] is False
    assert result.metrics["native_sparse_assembly_used"] is False
    assert result.metrics["sparse_factorization_count"] == 0
    assert result.metrics["sparse_factorization_diagnostic_hashes"] == []
    assert result.metrics["sparse_factorization_policy_hash"] is None
    assert result.metrics["sparse_factorization_diagnostics_passed"] is False
    assert result.configuration["equation_scaling"] == {
        "status": "unavailable",
        "reason": "no_free_reference_load",
    }
    assert result.metrics["terminal_physical_residual_trace_status"] == "unavailable"
    assert result.metrics["terminal_physical_residual_trace_reason"] == (
        "no_free_equations_no_convergence_claim"
    )
    assert "physical_equation_scaling_binding_hash" not in result.contract_bindings
    assert "terminal_physical_residual_trace_hash" not in result.contract_bindings
    assert result.convergence_history == ()
    assert result.node_displacements[-1]["UX_m"] == 1.0e-4
    assert result.support_reactions


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("sparse_factorization_diagnostics_passed", True),
        ("sparse_factorization_max_condition_number_1", 1.0),
        ("sparse_factorization_min_normalized_absolute_pivot", 1.0),
        ("sparse_factorization_max_backward_error", 0.0),
    ),
)
def test_extended_no_solve_rejects_rehashed_factorization_quality_credit(
    prescribed_only_result, field: str, value
) -> None:
    source = prescribed_only_result.to_dict()
    source["metrics"][field] = value
    source["result_hash"] = canonical_hash(
        {key: item for key, item in source.items() if key != "result_hash"}
    )
    with pytest.raises(
        ValueError, match="backend declaration differs from execution policy"
    ):
        validate_nonlinear_frame_manifest(source)


@pytest.mark.parametrize(
    "tamper",
    (
        "legacy-cap",
        "reaction-only",
        "reduced-factorization-count",
        "reaction-only-with-retained-bindings",
    ),
)
def test_extended_rejects_coherently_rehashed_backend_scope_downgrade(
    extended_case, tamper: str
) -> None:
    original = extended_case[2]
    source = original.to_dict()["result_ir"]
    assert source["convergence_history"]
    assert len(source["convergence_history"][0]["residual_kn"]) == 258
    if tamper == "legacy-cap":
        source["configuration"]["matrix_backend"] = VECTOR_SPARSE_MATRIX_BACKEND
        source["metrics"]["sparse_factorization_policy_hash"] = (
            SparseFactorizationPolicy().policy_hash
        )
    elif tamper == "reduced-factorization-count":
        assert len(source["convergence_history"]) > 1
        source["metrics"]["sparse_factorization_count"] = 1
        source["metrics"]["sparse_factorization_diagnostic_hashes"] = source["metrics"][
            "sparse_factorization_diagnostic_hashes"
        ][:1]
    else:
        source["metrics"].update(
            {
                "solver_executed": False,
                "no_solve_contract_pass": True,
                "sparse_backend_used": False,
                "native_sparse_assembly_used": False,
                "sparse_factorization_count": 0,
                "sparse_factorization_diagnostic_hashes": [],
                "sparse_factorization_policy_hash": None,
                "sparse_factorization_diagnostics_passed": False,
                "sparse_factorization_max_condition_number_1": None,
                "sparse_factorization_min_normalized_absolute_pivot": None,
                "sparse_factorization_max_backward_error": None,
            }
        )
        assert (
            source["metrics"]["terminal_physical_residual_trace_status"] == "available"
        )
        if tamper == "reaction-only-with-retained-bindings":
            source["convergence_history"] = []
            source["metrics"].update(
                {
                    "terminal_physical_residual_trace_status": "unavailable",
                    "terminal_physical_residual_trace_reason": (
                        "no_free_equations_no_convergence_claim"
                    ),
                    "terminal_physical_residual_trace_hash": None,
                }
            )
            source["configuration"]["equation_scaling"] = {
                "status": "unavailable",
                "reason": "no_free_reference_load",
            }
            bindings = source["contract_bindings"]
            assert bindings["physical_equation_scaling_binding_hash"]
            assert bindings["terminal_physical_residual_trace_hash"]
            assert (
                bindings["bounded_planar_execution_plan"]["equation_scaling_status"]
                == "available"
            )
            assert bindings == original.to_dict()["result_ir"]["contract_bindings"]
    source["result_hash"] = canonical_hash(
        {key: item for key, item in source.items() if key != "result_hash"}
    )
    with pytest.raises(
        ValueError, match="backend declaration differs from execution policy"
    ):
        validate_nonlinear_frame_manifest(source)
    with pytest.raises(
        ValueError, match="backend declaration differs from execution policy"
    ):
        validate_planar_frame_result(_rehash_outer(original, result_ir=source))


@pytest.mark.parametrize(
    ("section", "field", "value"),
    (
        ("metrics", "sparse_factorization_policy_hash", "sha256:" + "0" * 64),
        ("configuration", "matrix_backend", VECTOR_SPARSE_MATRIX_BACKEND),
        ("configuration", "matrix_backend", VECTOR_MATRIX_BACKEND),
        ("configuration", "stiffness_storage", "numpy_dense_ndarray"),
        ("metrics", "sparse_backend_used", False),
        ("metrics", "native_sparse_assembly_used", False),
        ("metrics", "sparse_factorization_count", True),
        ("metrics", "sparse_factorization_diagnostic_hashes", []),
        ("metrics", "sparse_factorization_diagnostics_passed", False),
        ("metrics", "sparse_factorization_max_condition_number_1", 1.0e12 + 1),
        ("metrics", "sparse_factorization_min_normalized_absolute_pivot", 1.0e-15),
        ("metrics", "sparse_factorization_max_backward_error", 1.0e-11),
        ("metrics", "sparse_factorization_max_condition_number_1", True),
        ("metrics", "sparse_factorization_min_normalized_absolute_pivot", None),
    ),
    ids=(
        "policy-hash",
        "legacy-backend",
        "dense-backend",
        "dense-storage",
        "sparse-flag",
        "native-csr-flag",
        "boolean-count",
        "missing-diagnostics",
        "failed-diagnostics",
        "condition-above-policy",
        "pivot-below-policy",
        "backward-error-above-policy",
        "boolean-condition",
        "missing-pivot",
    ),
)
def test_extended_public_rejects_rehashed_backend_and_policy_declarations(
    extended_case, section: str, field: str, value
) -> None:
    original = extended_case[2]
    source = deepcopy(original.to_dict()["result_ir"])
    source[section][field] = value
    if field == "matrix_backend" and value == VECTOR_MATRIX_BACKEND:
        # A coherent dense declaration must still disagree with sparse execution.
        source["configuration"]["stiffness_storage"] = "numpy_dense_ndarray"
    source["result_hash"] = canonical_hash(
        {key: item for key, item in source.items() if key != "result_hash"}
    )
    with pytest.raises(
        ValueError, match="backend declaration differs from execution policy"
    ):
        validate_nonlinear_frame_manifest(source)
    tampered = _rehash_outer(original, result_ir=source)
    with pytest.raises(
        ValueError, match="backend declaration differs from execution policy"
    ):
        validate_planar_frame_result(tampered)
