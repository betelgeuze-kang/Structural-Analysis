#!/usr/bin/env python3
"""Verify the bounded native sparse linear CPU C0/C1 evidence chain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOKENS = {
    "native/cpp/src/solver_cpu/sparse_linear.hpp": (
        "enum class SolverStatus",
        "SparseLinearExecutionState",
        "begin_sparse_spd_pcg",
        "advance_sparse_spd_pcg",
        "struct CsrMatrixView",
        "solve_sparse_spd_pcg",
        "fallback_count",
    ),
    "native/cpp/src/solver_cpu/sparse_linear.cpp": (
        "validate_canonical_csr",
        "validate_symmetric_structure_and_values",
        "SolverStatus::singularity",
        "SolverStatus::indefinite_operator",
        "SolverStatus::nonconvergence",
        "SolverStatus::increment_limit",
        "SolverStatus::residual_limit",
    ),
    "native/cpp/tests/solver_cpu/sparse_linear_test.cpp": (
        "solves_spd_and_is_bitwise_deterministic",
        "canonical_validation_fails_closed",
        "numerical_status_taxonomy_is_stable",
        "increment failure atomicity",
    ),
    "native/cpp/tests/solver_cpu/sparse_linear_parity_dump.cpp": (
        "spd5",
        "irregular6",
        "scaled4",
        "zero5",
    ),
    "native/cpp/tests/fuzz/sparse_linear_fuzz.cpp": (
        "LLVMFuzzerTestOneInput",
        "solve_sparse_spd_pcg",
        "std::invalid_argument",
    ),
    "native/cpp/include/structural/abi_v1.h": (
        "SA_ABI_V1_8",
        "SA_ABI_V1_10",
        "SA_CAPABILITY_SPARSE_LINEAR_CPU",
        "SA_CAPABILITY_SPARSE_LINEAR_RESTART_CPU",
        "sa_sparse_csr_matrix_v1",
        "sa_sparse_linear_solve_fn_v1",
        "sa_sparse_linear_state_v1",
        "sa_sparse_linear_begin_fn_v1",
        "sa_sparse_linear_advance_fn_v1",
    ),
    "native/cpp/tests/abi/sparse_linear_contract_test.cpp": (
        "table_is_append_only",
        "failures_do_not_publish_partial_outputs",
        "immutable_inputs_are_reentrant",
        "caller_owned_restart_is_complete_and_failure_atomic",
        "SA_ERR_SINGULARITY",
        "SA_ERR_INDEFINITE_OPERATOR",
    ),
    "native/crates/structural-ffi-sys/src/sparse_linear.rs": (
        "SaSparseCsrMatrixV1",
        "SaSparseLinearConfigV1",
        "SaSparseLinearResultV1",
    ),
    "native/crates/structural-ffi/src/lib.rs": (
        "load_sparse_linear",
        "load_sparse_linear_restart",
        "solve_sparse_linear",
        "native sparse linear result violated the v1.8 output contract",
    ),
    "native/crates/structural-ffi/tests/sparse_linear_parity.rs": (
        "numerical_error_taxonomy_crosses_the_safe_wrapper",
        "immutable_sparse_operation_is_reentrant_and_bitwise_deterministic",
        "SA_ERR_INCREMENT_LIMIT",
    ),
    "native/cpp/tests/fuzz/sparse_linear_abi_fuzz.cpp": (
        "sparse_linear_solve",
        "output_view.data = rhs.data()",
        "config.flags = 1U",
    ),
    "tests/test_native_sparse_linear_python_parity.py": (
        "independent_numpy_dense_solve",
        "np.linalg.solve",
        "np.linalg.eigvalsh",
        "fallback_count",
    ),
    "docs/native/sparse-linear-cpu-v1.md": (
        "C0",
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
    ),
}


def check_native_sparse_linear(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    try:
        payload = json.loads(
            (root / "native/capabilities.json").read_text(encoding="utf-8")
        )
        row = payload["capabilities"]["sparse_linear_solver_cpu"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        blockers.append(f"sparse_linear_capability_invalid:{exc}")
        row = {}
    if row.get("status") != "implemented":
        blockers.append("sparse_linear_capability_not_implemented")
    if row.get("cutover_gate") != "C1":
        blockers.append("sparse_linear_capability_gate_not_c1")
    if row.get("owner") != "structural_solver_cpu":
        blockers.append("sparse_linear_capability_owner_invalid")
    claim = str(row.get("claim", ""))
    for token in (
        "canonical CSR",
        "NumPy",
        "ABI v1.8",
        "ABI v1.10",
        "HIP C2",
        "iteration control resident",
        "native-hip-approved",
        "C6",
    ):
        if token not in claim:
            blockers.append(f"sparse_linear_capability_scope_token_missing:{token}")

    for relative, tokens in REQUIRED_TOKENS.items():
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"sparse_linear_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(
                    f"sparse_linear_evidence_token_missing:{relative}:{token}"
                )

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-sparse-linear-contract.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "cutover_gate": "C1" if not blockers else None,
        "blockers": blockers,
        "claim_boundary": (
            "This proves one bounded CPU canonical-CSR PCG family through C1. It does "
            "include local live HIP C2 and ABI v1.8/v1.10 Rust C3 implementation "
            "candidates, but does not promote protected C2 or subsequent C3. Separate "
            "bounded CPU evidence may implement C4/C5 without promoting this numerical "
            "family; this check does not close general sparse solvers or C6."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_native_sparse_linear(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native sparse linear CPU contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
