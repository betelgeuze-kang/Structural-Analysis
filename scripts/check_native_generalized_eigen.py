#!/usr/bin/env python3
"""Verify the bounded native modal/buckling generalized-eigen C0/C1 chain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOKENS = {
    "native/cpp/src/solver_cpu/generalized_eigen.hpp": (
        "struct DenseSymmetricMatrixView",
        "solve_dense_modal_modes",
        "solve_dense_linear_buckling",
        "fallback_count",
    ),
    "native/cpp/src/solver_cpu/generalized_eigen.cpp": (
        "symmetric_eigen_jacobi",
        "canonicalize_eigenspace",
        "requested mode_count cuts a repeated or clustered",
        "SolverStatus::nonconvergence",
        "SolverStatus::residual_limit",
    ),
    "native/cpp/tests/solver_cpu/generalized_eigen_test.cpp": (
        "modal_closed_form_rigid_scaling_and_repeat_are_exact",
        "repeated_eigenspaces_are_coordinate_axis_canonical",
        "buckling_filters_infinite_modes_and_recovers_scaling",
        "nonconvergence must not publish partial modes",
    ),
    "native/cpp/tests/solver_cpu/generalized_eigen_parity_dump.cpp": (
        "modal_scaled",
        "modal_rigid",
        "buckling_singular",
        "buckling_tiny",
    ),
    "native/cpp/tests/fuzz/generalized_eigen_fuzz.cpp": (
        "LLVMFuzzerTestOneInput",
        "solve_dense_modal_modes",
        "solve_dense_linear_buckling",
        "std::invalid_argument",
    ),
    "tests/test_native_generalized_eigen_python_parity.py": (
        "independent_scipy_oracle",
        "eigh",
        "buckling_singular",
        "fallback_count",
    ),
    "docs/native/generalized-eigen-cpu-v1.md": (
        "C0",
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
    ),
}


def check_native_generalized_eigen(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    try:
        payload = json.loads(
            (root / "native/capabilities.json").read_text(encoding="utf-8")
        )
        row = payload["capabilities"]["generalized_eigen_solver_cpu"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        blockers.append(f"generalized_eigen_capability_invalid:{exc}")
        row = {}
    if row.get("status") != "implemented":
        blockers.append("generalized_eigen_capability_not_implemented")
    if row.get("cutover_gate") != "C1":
        blockers.append("generalized_eigen_capability_gate_not_c1")
    if row.get("owner") != "structural_solver_cpu":
        blockers.append("generalized_eigen_capability_owner_invalid")
    claim = str(row.get("claim", ""))
    for token in ("modal", "buckling", "SciPy", "HIP C2", "ABI C3", "C6"):
        if token not in claim:
            blockers.append(f"generalized_eigen_capability_scope_token_missing:{token}")

    for relative, tokens in REQUIRED_TOKENS.items():
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"generalized_eigen_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(
                    f"generalized_eigen_evidence_token_missing:{relative}:{token}"
                )

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-generalized-eigen-contract.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "cutover_gate": "C1" if not blockers else None,
        "blockers": blockers,
        "claim_boundary": (
            "This proves one bounded dense symmetric modal/linear-buckling CPU family "
            "through C1. Sparse extraction, HIP C2, ABI/Rust C3, restart C4, product "
            "E2E C5 and C6 remain open."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_native_generalized_eigen(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native generalized eigen contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
