from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from typing import Any

import jsonschema
import numpy as np
import pytest
from scipy.sparse import csr_matrix

from structural_analysis.assembly.linear_static import assemble_linear_static_sparse
from structural_analysis.benchmark.medium_scale_execution import (
    CASE_SPECS,
    PROFILE_ID,
    _sha256_json,
    _symmetric_extreme_eigen_diagnostics,
    build_medium_scale_execution_receipt,
    build_medium_scale_model,
    execute_medium_scale_case,
    run_isolated_case,
    validate_medium_scale_execution_receipt,
)


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_medium_scale_current_source_profile.py"
SOURCE_SHA = "a" * 40


@pytest.fixture(scope="module")
def full_profile() -> dict[str, object]:
    return build_medium_scale_execution_receipt(
        source_commit_sha=SOURCE_SHA,
        source_tree_clean=True,
        worker_command=[sys.executable, str(RUNNER)],
    )


def test_medium_scale_case_policy_is_five_slot_and_models_are_deterministic() -> None:
    assert len(CASE_SPECS) == 5
    assert len({row.case_id for row in CASE_SPECS}) == 5
    assert len({row.archetype_id for row in CASE_SPECS}) == 5

    for spec in CASE_SPECS:
        first = build_medium_scale_model(spec.case_id)
        second = build_medium_scale_model(spec.case_id)
        assert first.input_checksum == second.input_checksum
        assert first.canonical_model_checksum == second.canonical_model_checksum
        assert first.metadata["scientific_medium_benchmark_credit"] is False
        assembly, unsupported = assemble_linear_static_sparse(first)
        assert unsupported == []
        assert assembly is not None
        free = set(assembly.active_dofs) - set(assembly.constrained_dofs)
        assert 257 <= len(free) <= 2_048


def test_one_medium_scale_case_runs_all_resource_and_numerical_gates() -> None:
    payload = execute_medium_scale_case("generated_braced_truss_tower")

    assert payload["contract_pass"] is True
    assert payload["technical_execution_credit"] is True
    assert payload["scientific_medium_benchmark_credit"] is False
    assert payload["native_medium_product_authority"] is False
    assert all(payload["gates"].values())
    assert payload["assembly_and_conditioning"]["free_equation_count"] == 288
    assert payload["assembly_and_conditioning"]["sparse_storage"] == "scipy_sparse_csr"
    assert payload["assembly_and_conditioning"]["factorization_backend"] == (
        "scipy_superlu_splu"
    )
    assert payload["assembly_and_conditioning"]["scaled_condition_estimate_2"] < 1.0e9
    assert payload["comparison"]["contract_pass"] is True
    assert payload["determinism"]["exact_match"] is True
    assert payload["crashed"] is False
    assert payload["oom"] is False


def test_condition_diagnostic_observes_negative_algebraic_eigenvalue() -> None:
    matrix = csr_matrix(np.diag(np.asarray([-10.0, 1.0, 2.0])))

    minimum, maximum, minimum_residual, maximum_residual = (
        _symmetric_extreme_eigen_diagnostics(matrix)
    )

    assert minimum == pytest.approx(-10.0)
    assert maximum == pytest.approx(2.0)
    assert minimum_residual <= 1.0e-12
    assert maximum_residual <= 1.0e-12


def test_full_current_source_profile_executes_five_cases_without_promoting_authority(
    full_profile: dict[str, object],
) -> None:
    payload = full_profile

    validate_medium_scale_execution_receipt(payload)
    assert payload["profile_id"] == PROFILE_ID
    assert payload["status"] == "technical_execution_ready_authority_blocked"
    assert payload["contract_pass"] is True
    assert payload["release_authority"] is False
    assert payload["summary"] == {
        "required_case_count": 5,
        "executed_case_count": 5,
        "technical_execution_credit_count": 5,
        "scientific_medium_benchmark_credit_count": 0,
        "native_medium_product_authority_count": 0,
        "all_case_ids_match_policy": True,
        "all_technical_execution_gates_pass": True,
        "scientific_medium_benchmark_5_of_5": False,
        "native_medium_product_authority_5_of_5": False,
    }
    assert [row["case_id"] for row in payload["cases"]] == [
        row.case_id for row in CASE_SPECS
    ]
    assert all(row["contract_pass"] for row in payload["cases"])
    assert all(row["worker_wall_seconds"] < 45.0 for row in payload["cases"])
    assert (
        "independent_reference_solver_receipts_missing" in payload["blockers_remaining"]
    )
    assert "native_frame_alpha_free_equation_limit_60" in payload["blockers_remaining"]
    assert "surrogates" in payload["claim_boundary"]


def test_aggregate_blocks_a_dirty_source_tree_even_when_cases_pass(
    monkeypatch: pytest.MonkeyPatch,
    full_profile: dict[str, object],
) -> None:
    ready_cases = {
        row["case_id"]: row
        for row in copy.deepcopy(full_profile["cases"])
    }

    def repeated_case(**kwargs: object) -> dict[str, object]:
        return copy.deepcopy(ready_cases[kwargs["case_id"]])

    monkeypatch.setattr(
        "structural_analysis.benchmark.medium_scale_execution.run_isolated_case",
        repeated_case,
    )
    payload = build_medium_scale_execution_receipt(
        source_commit_sha=SOURCE_SHA,
        source_tree_clean=False,
        worker_command=[sys.executable, str(RUNNER)],
    )

    assert payload["contract_pass"] is False
    assert payload["status"] == "technical_execution_blocked"
    assert "source_tree_not_clean" in payload["blockers_remaining"]


def test_isolated_worker_rejects_wrong_case_identity(tmp_path: Path) -> None:
    worker = tmp_path / "wrong_worker.py"
    worker.write_text(
        "import json\nprint(json.dumps({'case_id': 'wrong', 'contract_pass': True}))\n",
        encoding="utf-8",
    )

    payload = run_isolated_case(
        case_id="generated_steel_moment_frame_3d",
        worker_command=[sys.executable, str(worker)],
    )

    assert payload["contract_pass"] is False
    assert payload["worker_failure"]["kind"] == "worker_identity_mismatch"


def test_aggregate_retains_a_schema_valid_blocked_receipt_on_worker_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failed_case(**kwargs: object) -> dict[str, object]:
        return {
            "schema_version": "medium-scale-current-source-case.v1",
            "profile_id": PROFILE_ID,
            "case_id": kwargs["case_id"],
            "worker_failure": {"kind": "worker_timeout", "detail": "bounded timeout"},
            "worker_wall_seconds": 45.0,
            "crashed": False,
            "oom": False,
            "technical_execution_credit": False,
            "scientific_medium_benchmark_credit": False,
            "native_medium_product_authority": False,
            "contract_pass": False,
            "authority_blockers": ["worker_timeout"],
        }

    monkeypatch.setattr(
        "structural_analysis.benchmark.medium_scale_execution.run_isolated_case",
        failed_case,
    )
    payload = build_medium_scale_execution_receipt(
        source_commit_sha=SOURCE_SHA,
        source_tree_clean=True,
        worker_command=[sys.executable, str(RUNNER)],
    )

    validate_medium_scale_execution_receipt(payload)
    assert payload["status"] == "technical_execution_blocked"
    assert payload["contract_pass"] is False
    assert payload["summary"]["technical_execution_credit_count"] == 0
    assert (
        "technical_medium_scale_execution_incomplete:0/5"
        in payload["blockers_remaining"]
    )


def test_schema_forbids_scientific_or_native_promotion_without_evidence(
    full_profile: dict[str, object],
) -> None:
    payload = copy.deepcopy(full_profile)
    payload["cases"][0]["scientific_medium_benchmark_credit"] = True

    with pytest.raises(jsonschema.ValidationError):
        validate_medium_scale_execution_receipt(payload)


def test_semantic_validator_rejects_summary_credit_tamper(
    full_profile: dict[str, object],
) -> None:
    payload = copy.deepcopy(full_profile)
    observed = payload["summary"]["technical_execution_credit_count"]
    payload["summary"]["technical_execution_credit_count"] = (
        0 if observed != 0 else 1
    )

    with pytest.raises(ValueError, match="summary_count_mismatch"):
        validate_medium_scale_execution_receipt(payload)


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("cases", 0, "comparison", "contract_pass"), False),
        (("cases", 0, "determinism", "exact_match"), False),
        (("cases", 0, "solver", "sparse_backend"), "forged_backend"),
        (("cases", 0, "solver", "sparse_first_relative_residual"), 1.0),
        (("cases", 0, "worker_wall_seconds"), 999.0),
        (("cases", 0, "worker_wall_seconds"), 0.0),
        (("cases", 0, "crashed"), True),
        (("cases", 0, "oom"), True),
        (
            ("cases", 0, "assembly_and_conditioning", "minimum_scaled_eigenvalue"),
            -1.0,
        ),
        (
            ("cases", 0, "assembly_and_conditioning", "conditioning_gate_pass"),
            False,
        ),
        (("cases", 0, "assembly_and_conditioning", "free_equation_count"), 300),
        (
            ("cases", 0, "solver", "run_observations", 2, "stiffness_storage"),
            "forged_dense_storage",
        ),
        (("policy", "scaled_condition_estimate_limit"), 1.0e99),
        (("environment", "analysis_engine_version"), "forged-version"),
        (("blockers_remaining", 0), "forged_blocker"),
    ],
)
def test_semantic_validator_rejects_credit_bearing_receipt_tamper(
    full_profile: dict[str, object],
    path: tuple[object, ...],
    replacement: object,
) -> None:
    payload = copy.deepcopy(full_profile)
    target: Any = payload
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = replacement

    with pytest.raises((jsonschema.ValidationError, ValueError)):
        validate_medium_scale_execution_receipt(payload)


def _rebind_receipt_digest(payload: dict[str, object]) -> None:
    payload.pop("receipt_payload_sha256")
    payload["receipt_payload_sha256"] = _sha256_json(payload)


def test_current_source_replay_rejects_coherently_rebound_condition_tamper(
    full_profile: dict[str, object],
) -> None:
    payload = copy.deepcopy(full_profile)
    diagnostics = payload["cases"][0]["assembly_and_conditioning"]
    diagnostics.update(
        {
            "minimum_scaled_eigenvalue": 1.0,
            "maximum_scaled_eigenvalue": 2.0,
            "minimum_eigenpair_relative_residual": 0.0,
            "maximum_eigenpair_relative_residual": 0.0,
            "scaled_condition_estimate_2": 2.0,
        }
    )
    _rebind_receipt_digest(payload)

    with pytest.raises(ValueError, match="case_current_source_replay_mismatch"):
        validate_medium_scale_execution_receipt(payload)


def test_current_source_replay_rejects_coherently_rebound_comparison_tamper(
    full_profile: dict[str, object],
) -> None:
    payload = copy.deepcopy(full_profile)
    families = payload["cases"][0]["comparison"]["families"]
    for metric in families.values():
        metric["max_absolute_difference"] = 0.0
        metric["reference_linf_norm"] = 0.0
        metric["relative_linf_difference"] = 0.0
    _rebind_receipt_digest(payload)

    with pytest.raises(ValueError, match="case_current_source_replay_mismatch"):
        validate_medium_scale_execution_receipt(payload)


def test_rebound_authority_and_environment_text_still_fail_closed(
    full_profile: dict[str, object],
) -> None:
    for path, replacement in (
        (
            ("claim_boundary",),
            "This forged claim asserts full independent V&V, unrestricted design authority, "
            "and release authority for every medium-scale product path.",
        ),
        (("environment", "platform"), "forged-platform"),
    ):
        payload = copy.deepcopy(full_profile)
        target: Any = payload
        for component in path[:-1]:
            target = target[component]
        target[path[-1]] = replacement
        _rebind_receipt_digest(payload)

        with pytest.raises(ValueError):
            validate_medium_scale_execution_receipt(payload)


def test_json_receipt_contains_no_non_finite_values() -> None:
    payload = execute_medium_scale_case("generated_steel_moment_frame_3d")
    encoded = json.dumps(payload, allow_nan=False)
    assert encoded


def test_current_source_workflow_attests_only_non_promoting_main_receipt() -> None:
    workflow = (ROOT / ".github/workflows/medium-scale-current-source.yml").read_text(
        encoding="utf-8"
    )

    assert 'SOURCE_SHA: "${{ github.sha }}"' in workflow
    assert "runs-on: ubuntu-22.04" in workflow
    assert '--source-sha "$SOURCE_SHA"' in workflow
    assert 'technical_execution_credit_count"] == 5' in workflow
    assert 'scientific_medium_benchmark_credit_count"] == 0' in workflow
    assert 'native_medium_product_authority_count"] == 0' in workflow
    assert "actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d" in workflow
    assert (
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    )
    assert "--deny-self-hosted-runners" in workflow
