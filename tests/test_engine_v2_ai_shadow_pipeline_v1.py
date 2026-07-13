from __future__ import annotations

import ast
from pathlib import Path
import sys

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2 import (  # noqa: E402
    build_fixed_rank_projection,
    build_phase0_ai_proposal,
    compile_execution_plan,
    create_fixed_rank_qr_memory,
    create_initial_state,
    execute_linear_static_plan_v1,
    pack_solver_model_buffers,
    run_ai_shadow_v1,
    update_fixed_rank_qr_memory_from_run,
    validate_fixed_rank_qr_memory,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
AI_SOURCE_DIR = SRC_ROOT / "structural_analysis/engine_v2/ai"


def _pipeline_artifacts():
    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id="LC_WEAK"
    )
    plan = compile_execution_plan(buffers)
    accepted = create_initial_state(plan)
    free = np.asarray(plan.free_dofs, dtype=np.int64)
    stiffness_ff = plan.operator.stiffness_matrix[np.ix_(free, free)]
    solution_free = np.linalg.solve(
        stiffness_ff, plan.operator.load_vector[free]
    )
    projection = build_fixed_rank_projection(
        plan,
        solution_free.reshape((-1, 1)),
        rank_cap=2,
    )
    solution_scaled = solution_free / projection.scaling_diagonal
    coefficients = projection.basis_q.T @ solution_scaled
    trust_radius = max(1.0e-12, float(np.linalg.norm(coefficients)) * 1.01)
    proposal = build_phase0_ai_proposal(
        plan,
        accepted,
        projection,
        coefficients,
        trust_radius,
    )
    return buffers, plan, accepted, proposal


def test_shadow_pipeline_keeps_authoritative_result_and_receipt_chain_exact() -> None:
    buffers, plan, accepted, proposal = _pipeline_artifacts()
    baseline = execute_linear_static_plan_v1(buffers, plan)

    shadow = run_ai_shadow_v1(buffers, plan, accepted, proposal)
    after_shadow = execute_linear_static_plan_v1(buffers, plan)

    assert shadow.gate_receipt.status == "rejected"
    assert shadow.gate_receipt.reason_codes == (
        "ood_not_evaluated",
        "statistical_calibration_missing",
    )
    assert shadow.proposal_consumed_by_authoritative_solver is False
    assert shadow.parity.all_authoritative_outputs_bit_identical is True
    assert (
        baseline.backend_result.result_hash
        == shadow.ai_off_run.backend_result.result_hash
        == shadow.ai_on_run.backend_result.result_hash
        == after_shadow.backend_result.result_hash
    )
    assert (
        baseline.result_ir.result_ir_hash
        == shadow.ai_off_run.result_ir.result_ir_hash
        == shadow.ai_on_run.result_ir.result_ir_hash
        == after_shadow.result_ir.result_ir_hash
    )
    assert (
        baseline.receipt_chain_hash
        == shadow.ai_off_run.receipt_chain_hash
        == shadow.ai_on_run.receipt_chain_hash
        == after_shadow.receipt_chain_hash
    )


def test_qr_memory_accepts_only_authoritative_shadow_runs_as_teachers() -> None:
    buffers, plan, accepted, proposal = _pipeline_artifacts()
    shadow = run_ai_shadow_v1(buffers, plan, accepted, proposal)
    memory = create_fixed_rank_qr_memory(plan, rank_cap=2)

    first = update_fixed_rank_qr_memory_from_run(memory, shadow.ai_off_run)
    second = update_fixed_rank_qr_memory_from_run(first, shadow.ai_on_run)

    assert second.active_teacher_count == 2
    assert second.accepted_teacher_count_total == 2
    assert second.retained_rank == 1
    assert second.provenance[0].receipt_chain_hash == (
        shadow.ai_off_run.receipt_chain_hash
    )
    assert second.provenance[1].receipt_chain_hash == (
        shadow.ai_on_run.receipt_chain_hash
    )
    assert all(
        row.receipt_chain_hash != shadow.gate_receipt.gate_receipt_hash
        for row in second.provenance
    )
    validate_fixed_rank_qr_memory(second, expected_plan=plan)


def test_shipped_phase0_ai_path_has_no_ml_framework_or_backward_dependency() -> None:
    forbidden_import_roots = {"autograd", "jax", "tensorflow", "torch"}
    forbidden_calls = {"backward", "grad"}

    for source_path in sorted(AI_SOURCE_DIR.glob("*.py")):
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_roots: set[str] = set()
        called_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(
                    alias.name.split(".", 1)[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called_names.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    called_names.add(node.func.attr)

        assert not imported_roots.intersection(forbidden_import_roots), source_path
        assert not called_names.intersection(forbidden_calls), source_path
        assert "implementation.phase1" not in source
        assert "structural_analysis.ai" not in source
