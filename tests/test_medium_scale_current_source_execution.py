from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
import subprocess
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
    PEAK_MEMORY_LIMIT_BYTES,
    _oracle_model_payload,
    _sha256_json,
    _strict_json_loads,
    _symmetric_extreme_eigen_diagnostics,
    build_medium_scale_execution_receipt,
    build_medium_scale_model,
    execute_medium_scale_case,
    run_isolated_case,
    validate_medium_scale_execution_receipt,
)
from structural_analysis.benchmark.medium_scale_independent_oracle import (
    NORMALIZATION_POLICY,
    ORACLE_ID,
    run_independent_medium_oracle,
)


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_medium_scale_current_source_profile.py"
SOURCE_SHA = "a" * 40


@pytest.mark.parametrize(
    "raw",
    [
        '{"case_id":"a","case_id":"b"}',
        '{"metric":NaN}',
        '{"metric":Infinity}',
        '{"metric":1e9999}',
    ],
)
def test_medium_raw_json_rejects_duplicate_keys_and_nonfinite_numbers(
    raw: str,
) -> None:
    with pytest.raises(ValueError, match="duplicate_json_key|nonfinite_json"):
        _strict_json_loads(raw, label="attack")


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
    # Resource gates are defined over the isolated worker process lifetime.
    # Running the case in the pytest process would instead compare pytest's
    # pre-existing peak RSS (including plugins and earlier tests) with the
    # case limit, which can fail even when the production worker stays well
    # below the bound.
    payload = run_isolated_case(
        case_id="generated_braced_truss_tower",
        worker_command=[sys.executable, str(RUNNER)],
    )

    assert "worker_failure" not in payload
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
    assert payload["internal_oracle_comparison"]["contract_pass"] is True
    assert payload["internal_oracle_comparison"]["reference_implementation"] == (
        ORACLE_ID
    )
    assert payload["internal_oracle_comparison"]["normalization_policy"] == (
        NORMALIZATION_POLICY
    )
    assert payload["determinism"]["exact_match"] is True
    assert payload["crashed"] is False
    assert payload["oom"] is False
    assert payload["resources"]["observation_authority"] == (
        "non_authoritative_pre_attestation_observation"
    )
    assert payload["resources"]["authority_requires"] == (
        "verified_exact_source_github_provenance_attestation"
    )


def test_internal_oracle_is_a_separate_source_boundary_and_deterministic() -> None:
    source_path = (
        ROOT / "src/structural_analysis/benchmark/medium_scale_independent_oracle.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        str(node.module) for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    )
    assert not any(
        name.startswith(
            (
                "structural_analysis.api",
                "structural_analysis.assembly",
                "structural_analysis.elements",
                "structural_analysis.solvers",
            )
        )
        for name in imported
    )

    model = build_medium_scale_model("generated_braced_truss_tower")
    first = run_independent_medium_oracle(_oracle_model_payload(model))
    second = run_independent_medium_oracle(_oracle_model_payload(model))
    assert first["oracle_id"] == ORACLE_ID
    assert first["truth_class"] == "same_repository_independent_implementation"
    assert first["normalization_policy"] == NORMALIZATION_POLICY
    assert first["raw_result_sha256"] == second["raw_result_sha256"]
    assert first["normalized_result_sha256"] == second["normalized_result_sha256"]
    assert first["relative_residual"] <= 1.0e-8
    assert first["free_dof_count"] == 288
    assert "not an external solver" in first["authority_boundary"]


def test_internal_oracle_fails_closed_outside_its_bounded_semantics() -> None:
    model = build_medium_scale_model("generated_steel_moment_frame_3d")
    payload = _oracle_model_payload(model)
    payload["elements"][0]["local_axis_angle_deg"] = 10.0

    with pytest.raises(ValueError, match="outside_oracle_subset"):
        run_independent_medium_oracle(payload)

    truss_model = build_medium_scale_model("generated_braced_truss_tower")
    inactive_load_payload = _oracle_model_payload(truss_model)
    inactive_load_payload["loads"][0]["components"]["MX"] = 1.0
    with pytest.raises(ValueError, match="load_on_inactive_equation"):
        run_independent_medium_oracle(inactive_load_payload)


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
        "independent_internal_oracle_comparison_count": 5,
        "scientific_medium_benchmark_credit_count": 0,
        "native_medium_product_authority_count": 0,
        "all_case_ids_match_policy": True,
        "all_technical_execution_gates_pass": True,
        "independent_internal_oracle_comparison_5_of_5": True,
        "scientific_medium_benchmark_5_of_5": False,
        "native_medium_product_authority_5_of_5": False,
    }
    assert [row["case_id"] for row in payload["cases"]] == [
        row.case_id for row in CASE_SPECS
    ]
    assert all(row["contract_pass"] for row in payload["cases"])
    assert all(row["worker_wall_seconds"] < 45.0 for row in payload["cases"])
    assert "external_reference_solver_receipts_missing" in payload["blockers_remaining"]
    assert "native_frame_alpha_free_equation_limit_60" in payload["blockers_remaining"]
    assert "surrogates" in payload["claim_boundary"]


def test_aggregate_blocks_a_dirty_source_tree_even_when_cases_pass(
    monkeypatch: pytest.MonkeyPatch,
    full_profile: dict[str, object],
) -> None:
    ready_cases = {row["case_id"]: row for row in copy.deepcopy(full_profile["cases"])}

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


def test_partial_worker_output_becomes_a_valid_blocked_aggregate_receipt(
    tmp_path: Path,
) -> None:
    worker = tmp_path / "partial_worker.py"
    worker.write_text(
        "import json, sys\n"
        "print(json.dumps({'case_id': sys.argv[-1], 'contract_pass': True}))\n",
        encoding="utf-8",
    )

    payload = build_medium_scale_execution_receipt(
        source_commit_sha=SOURCE_SHA,
        source_tree_clean=True,
        worker_command=[sys.executable, str(worker)],
    )

    validate_medium_scale_execution_receipt(payload)
    assert payload["contract_pass"] is False
    assert payload["summary"]["technical_execution_credit_count"] == 0
    assert all(
        row["worker_failure"]["kind"] == "worker_contract_invalid"
        for row in payload["cases"]
    )
    assert all(
        row["authority_blockers"] == ["worker_contract_invalid"]
        for row in payload["cases"]
    )
    assert all(row["crashed"] is False for row in payload["cases"])
    assert all(row["oom"] is False for row in payload["cases"])
    assert (
        sum(
            blocker.startswith("medium_scale_case_failure:")
            for blocker in payload["blockers_remaining"]
        )
        == 5
    )


def test_nonzero_worker_becomes_a_crashed_blocked_aggregate_receipt(
    tmp_path: Path,
) -> None:
    worker = tmp_path / "nonzero_worker.py"
    worker.write_text("raise SystemExit(7)\n", encoding="utf-8")

    payload = build_medium_scale_execution_receipt(
        source_commit_sha=SOURCE_SHA,
        source_tree_clean=True,
        worker_command=[sys.executable, str(worker)],
    )

    validate_medium_scale_execution_receipt(payload)
    assert payload["contract_pass"] is False
    assert all(
        row["worker_failure"]["kind"] == "worker_nonzero_exit"
        for row in payload["cases"]
    )
    assert all(row["crashed"] is True for row in payload["cases"])
    assert all(row["oom"] is False for row in payload["cases"])


def test_gate_failing_worker_receipt_is_preserved_despite_exit_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker_payload = execute_medium_scale_case("generated_steel_moment_frame_3d")
    worker_payload["resources"]["peak_memory_bytes"] = PEAK_MEMORY_LIMIT_BYTES + 1
    worker_payload["gates"]["peak_memory"] = False
    worker_payload["technical_execution_credit"] = False
    worker_payload["contract_pass"] = False

    monkeypatch.setattr(
        "structural_analysis.benchmark.medium_scale_execution.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout=json.dumps(worker_payload),
            stderr="",
        ),
    )

    payload = run_isolated_case(
        case_id="generated_steel_moment_frame_3d",
        worker_command=[sys.executable, str(RUNNER)],
    )

    assert "worker_failure" not in payload
    assert payload["gates"]["peak_memory"] is False
    assert payload["contract_pass"] is False
    assert payload["crashed"] is False
    assert payload["oom"] is False


def test_silent_sigkill_fails_closed_as_possible_oom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "structural_analysis.benchmark.medium_scale_execution.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[], returncode=-9, stdout="", stderr=""
        ),
    )

    payload = run_isolated_case(
        case_id="generated_steel_moment_frame_3d",
        worker_command=[sys.executable, str(RUNNER)],
    )

    assert payload["worker_failure"] == {
        "kind": "worker_signal",
        "detail": "worker exited with return code -9",
        "returncode": -9,
    }
    assert payload["crashed"] is True
    assert payload["oom"] is True


def test_timeout_worker_is_normalized_with_its_actual_wall_limit(
    tmp_path: Path,
) -> None:
    worker = tmp_path / "timeout_worker.py"
    worker.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")

    payload = run_isolated_case(
        case_id="generated_steel_moment_frame_3d",
        worker_command=[sys.executable, str(worker)],
        timeout_seconds=0.05,
    )

    assert payload["worker_failure"]["kind"] == "worker_timeout"
    assert payload["worker_timeout_limit_seconds"] == 0.05
    assert payload["worker_wall_seconds"] >= 0.05
    assert payload["crashed"] is False
    assert payload["oom"] is False
    assert payload["authority_blockers"] == ["worker_timeout"]


def test_aggregate_retains_a_schema_valid_blocked_receipt_on_worker_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failed_case(**kwargs: object) -> dict[str, object]:
        return {
            "schema_version": "medium-scale-current-source-case.v1",
            "profile_id": PROFILE_ID,
            "case_id": kwargs["case_id"],
            "worker_failure": {
                "kind": "worker_timeout",
                "detail": "bounded timeout",
                "returncode": None,
            },
            "worker_wall_seconds": 45.0,
            "worker_timeout_limit_seconds": 45.0,
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
    payload["summary"]["technical_execution_credit_count"] = 0 if observed != 0 else 1

    with pytest.raises(ValueError, match="summary_count_mismatch"):
        validate_medium_scale_execution_receipt(payload)


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("cases", 0, "comparison", "contract_pass"), False),
        (("cases", 0, "internal_oracle_comparison", "contract_pass"), False),
        (("cases", 0, "internal_oracle_comparison", "binding_pass"), False),
        (
            ("cases", 0, "internal_oracle_comparison", "model_canonical_checksum"),
            "sha256:" + "0" * 64,
        ),
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


def test_rebound_impossible_resource_observations_fail_closed(
    full_profile: dict[str, object],
) -> None:
    excessive = copy.deepcopy(full_profile)
    excessive["cases"][0]["assembly_and_conditioning"]["factorization_seconds"] = (
        100_000.0
    )
    _rebind_receipt_digest(excessive)
    with pytest.raises((jsonschema.ValidationError, ValueError)):
        validate_medium_scale_execution_receipt(excessive)

    zeroed = copy.deepcopy(full_profile)
    first = zeroed["cases"][0]
    first["assembly_and_conditioning"]["factorization_seconds"] = 0.0
    first["solver"]["sparse_first_seconds"] = 0.0
    first["solver"]["sparse_repeat_seconds"] = 0.0
    first["solver"]["dense_seconds"] = 0.0
    first["resources"]["execution_seconds"] = 0.0
    first["resources"]["peak_memory_bytes"] = 1
    first["worker_wall_seconds"] = 0.0
    _rebind_receipt_digest(zeroed)
    with pytest.raises((jsonschema.ValidationError, ValueError)):
        validate_medium_scale_execution_receipt(zeroed)


def test_rebound_resource_measurement_must_match_execution_platform(
    full_profile: dict[str, object],
) -> None:
    payload = copy.deepcopy(full_profile)
    resources = payload["cases"][0]["resources"]
    current = resources["measurement"]
    resources["measurement"] = (
        "Windows GetProcessMemoryInfo PeakWorkingSetSize"
        if current == "resource.getrusage(RUSAGE_SELF).ru_maxrss"
        else "resource.getrusage(RUSAGE_SELF).ru_maxrss"
    )
    _rebind_receipt_digest(payload)

    with pytest.raises(ValueError, match="case_gate_derivation_mismatch"):
        validate_medium_scale_execution_receipt(payload)


def test_rebound_failure_receipt_semantics_are_strict(tmp_path: Path) -> None:
    worker = tmp_path / "partial_worker.py"
    worker.write_text(
        "import json, sys\n"
        "print(json.dumps({'case_id': sys.argv[-1], 'contract_pass': True}))\n",
        encoding="utf-8",
    )
    blocked = build_medium_scale_execution_receipt(
        source_commit_sha=SOURCE_SHA,
        source_tree_clean=True,
        worker_command=[sys.executable, str(worker)],
    )

    mutations = (
        (("cases", 0, "worker_failure", "kind"), "worker_signal"),
        (("cases", 0, "crashed"), True),
        (("cases", 0, "oom"), True),
        (("cases", 0, "worker_wall_seconds"), 46.0),
        (("cases", 0, "authority_blockers"), ["forged_blocker"]),
    )
    for path, replacement in mutations:
        payload = copy.deepcopy(blocked)
        target: Any = payload
        for component in path[:-1]:
            target = target[component]
        target[path[-1]] = replacement
        _rebind_receipt_digest(payload)

        with pytest.raises((jsonschema.ValidationError, ValueError)):
            validate_medium_scale_execution_receipt(payload)


def test_json_receipt_contains_no_non_finite_values() -> None:
    payload = execute_medium_scale_case("generated_steel_moment_frame_3d")
    encoded = json.dumps(payload, allow_nan=False)
    assert encoded


def test_current_source_workflow_attests_only_non_promoting_main_receipt() -> None:
    workflow = (ROOT / ".github/workflows/medium-scale-current-source.yml").read_text(
        encoding="utf-8"
    )
    verifier = (ROOT / ".github/workflows/_technical-evidence-attest.yml").read_text(
        encoding="utf-8"
    )
    producer = workflow.split("  produce:\n", 1)[1].split("\n  attest:\n", 1)[0]

    assert "SOURCE_SHA: ${{ github.sha }}" in workflow
    assert "runs-on: ubuntu-24.04" in producer
    assert '--source-sha "$SOURCE_SHA"' in workflow
    assert "name: produce-unprivileged" in producer
    assert 'GH_TOKEN: ""' in producer
    assert "id-token: write" not in producer
    assert "attestations: write" not in producer
    assert "artifact-id: ${{ steps.handoff.outputs.artifact-id }}" in producer
    assert "artifact-digest: ${{ steps.handoff.outputs.artifact-digest }}" in producer
    assert "uses: ./.github/workflows/_technical-evidence-attest.yml" in workflow
    assert 'summary.get("technical_execution_credit_count") == 5' in verifier
    assert 'summary.get("independent_internal_oracle_comparison_count") == 5' in verifier
    assert 'summary.get("scientific_medium_benchmark_credit_count") == 0' in verifier
    assert 'summary.get("native_medium_product_authority_count") == 0' in verifier
    assert "actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d" in verifier
    assert (
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    )
    assert "subject-path: ${{ runner.temp }}/verified-technical-handoff/${{ inputs.receipt-path }}" in verifier
