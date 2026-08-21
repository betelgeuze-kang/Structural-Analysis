#!/usr/bin/env python3
"""Verify the bounded CPU material/element/assembly C1 evidence chain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOKENS = {
    "native/cpp/CMakeLists.txt": (
        "add_library(structural_model_assembly",
        "structural_model_ir",
        "structural_elements",
        "structural_assembly",
    ),
    "native/cpp/src/materials/materials.cpp": (
        "BilinearUniaxialPoint::trial",
        "BilinearUniaxialPoint::commit",
        "BilinearUniaxialPoint::rollback",
    ),
    "native/cpp/src/elements/reference_elements.cpp": (
        "evaluate_truss3d",
        "evaluate_frame3d",
        "evaluate_shell3_membrane",
        "finish_response",
    ),
    "native/cpp/src/assembly/dense_assembly.hpp": (
        "CanonicalCsrAssemblyResult",
        "active_dof_indices",
        "row_offsets",
        "column_indices",
        "assemble_reduced_csr_deterministic",
    ),
    "native/cpp/src/assembly/dense_assembly.cpp": (
        "stable_index",
        "assemble_reduced_csr_deterministic",
        "element stable indices must be unique",
        "element contribution references an out-of-range DOF",
        "constrained DOF indices must be unique",
        "constraint reduction must retain at least one active DOF",
        "sparse assembly accumulation exceeds the finite numerical domain",
    ),
    "native/cpp/src/model_ir/model_ir.hpp": (
        "LinearReferenceGraph",
        "project_linear_reference_graph",
    ),
    "native/cpp/src/model_ir/model_ir.cpp": (
        "Model::project_linear_reference_graph",
        "linear frame3d/truss3d reference slice",
        "output.constrained_dof_values.push_back",
        "requires linear-static patterns",
    ),
    "native/cpp/src/assembly/model_ir_assembly.hpp": (
        "ModelIrLinearAssemblyResult",
        "model_content_hash",
        "model_semantic_hash",
        "model_provenance_hash",
        "equilibrium_residual",
        "element_recovery",
        "assemble_model_ir_linear_reference",
    ),
    "native/cpp/src/assembly/model_ir_assembly.cpp": (
        "evaluate_frame3d",
        "evaluate_truss3d",
        "assemble_reduced_csr_deterministic",
        "constrained DOFs require the exact prescribed state and zero direction",
        "nodal-load accumulation exceeds the finite numerical domain",
        "self-weight equivalent-load assembly exceeds the finite numerical domain",
    ),
    "native/cpp/include/structural/abi_v1.h": (
        "SA_ABI_V1_7",
        "SA_CAPABILITY_REFERENCE_ELEMENTS_CPU",
        "reference_element_evaluate",
        "SA_ABI_V1_13",
        "SA_CAPABILITY_MODEL_IR_LINEAR_ASSEMBLY_CPU",
        "SA_MODEL_IR_LINEAR_MAX_GLOBAL_DOF_COUNT",
        "SA_MODEL_IR_LINEAR_MAX_STRUCTURAL_ENTRIES",
        "model_ir_linear_assembly_sizes",
        "model_ir_linear_assemble",
        "SA_ABI_V1_14",
        "SA_CAPABILITY_MODEL_IR_LINEAR_REACTIONS_CPU",
        "model_ir_linear_reaction_sizes",
        "model_ir_linear_reactions",
    ),
    "native/cpp/tests/abi/reference_elements_contract_test.cpp": (
        "table_is_append_only",
        "failures_do_not_publish_partial_outputs",
        "SA_EXECUTION_BACKEND_CPU",
    ),
    "native/cpp/tests/CMakeLists.txt": (
        "structural_model_ir_assembly_cpu_tests",
        "structural_model_ir_linear_assembly_abi_tests",
        "structural_model_assembly",
    ),
    "native/cpp/tests/abi/model_ir_linear_assembly_contract_test.cpp": (
        "table_is_append_only",
        "constrained_reactions_are_atomic_deterministic_and_concurrent",
        "successful_assembly_is_canonical_and_deterministic",
        "failures_are_atomic_and_aliases_fail_closed",
        "immutable_calls_are_concurrent",
    ),
    "native/cpp/tests/fuzz/CMakeLists.txt": (
        "structural_model_ir_linear_assembly_abi_fuzz",
        "structural_model_ir_linear_assembly_abi_fuzz_smoke",
        "structural_model_ir_linear_reactions_abi_fuzz",
        "structural_model_ir_linear_reactions_abi_fuzz_smoke",
    ),
    "native/cpp/tests/fuzz/model_ir_linear_assembly_abi_fuzz.cpp": (
        "LLVMFuzzerTestOneInput",
        "model_ir_linear_assembly_sizes",
        "model_ir_linear_assemble",
        "storage == storage_before",
    ),
    "native/cpp/tests/fuzz/model_ir_linear_reactions_abi_fuzz.cpp": (
        "LLVMFuzzerTestOneInput",
        "model_ir_linear_reaction_sizes",
        "model_ir_linear_reactions",
        "storage == storage_before",
    ),
    "native/cpp/tests/package_consumer/main.c": (
        "SA_CAPABILITY_MODEL_IR_LINEAR_ASSEMBLY_CPU",
        "model_ir_linear_assembly_sizes",
        "model_ir_linear_assemble",
        "SA_ABI_V1_14",
        "SA_CAPABILITY_MODEL_IR_LINEAR_REACTIONS_CPU",
        "model_ir_linear_reaction_sizes",
        "model_ir_linear_reactions",
    ),
    "native/crates/structural-ffi-sys/src/model_ir_linear_assembly.rs": (
        "SA_ABI_V1_13",
        "SaModelIrLinearAssemblySizesV1",
        "SaModelIrLinearAssemblyOutputsV1",
        "SaModelIrLinearAssembleFnV1",
    ),
    "native/crates/structural-ffi-sys/src/model_ir_linear_reactions.rs": (
        "SA_ABI_V1_14",
        "SaModelIrLinearReactionSizesV1",
        "SaModelIrLinearReactionOutputsV1",
        "SaModelIrLinearReactionsFnV1",
    ),
    "native/crates/structural-ffi/src/lib.rs": (
        "load_reference_elements",
        "evaluate_reference_element",
        "native reference element violated the v1.7 output contract",
        "load_model_ir_linear_assembly",
        "assemble_linear_reference",
        "native ModelIR linear assembly violated the v1.13 output contract",
        "load_model_ir_linear_reactions",
        "recover_linear_reactions",
        "native ModelIR linear reactions violated the v1.14 output contract",
    ),
    "native/crates/structural-ffi/tests/reference_elements_parity.rs": (
        "immutable_reference_operation_is_reentrant_and_deterministic",
        "fallback_count",
    ),
    "native/crates/structural-ffi/tests/model_ir_linear_assembly.rs": (
        "v1_13_safe_wrapper_preserves_identity_and_canonical_csr",
        "older_model_ir_table_cannot_claim_the_appended_operation",
        "immutable_model_assembly_is_safe_for_concurrent_reads",
    ),
    "native/crates/structural-ffi/tests/model_ir_linear_reactions.rs": (
        "v1_14_safe_wrapper_recovers_canonical_support_reactions",
        "older_model_ir_table_cannot_claim_reaction_slots",
        "immutable_reaction_recovery_is_safe_for_concurrent_reads",
    ),
    "tests/test_native_reference_elements_python_parity.py": (
        "independent_numpy_oracle",
        "truss.tangent",
        "assembly.tangent",
        "_reduced_csr_assembly_oracle",
        "assembly_csr.row_offsets",
        "assembly_csr.column_indices",
    ),
    "tests/test_native_model_ir_assembly_python_parity.py": (
        "typed_model_ir_mixed_graph_assembly_matches_independent_numpy_oracle",
        "model_assembly.equilibrium_residual",
        "model_assembly.frame_recovery",
        "model_assembly.truss_recovery",
    ),
    "docs/native/reference-elements-assembly-v1.md": (
        "C0",
        "C1",
        "authoritatively closed",
        "C6",
    ),
    "docs/native/modelir-linear-reference-assembly-v1.md": (
        "18-DOF graph",
        "43 structural entries",
        "equilibrium_residual = internal_force - external_load",
        "ABI v1.13",
        "ABI v1.14",
        "C3 integration candidate",
        "self-hashed reaction ResultIR",
        "installed distribution v84",
        "rootfs diagnostic",
        "prescribed-support initial internal force/effective RHS",
        "C6",
    ),
}


def check_native_reference_elements(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    try:
        payload = json.loads(
            (root / "native/capabilities.json").read_text(encoding="utf-8")
        )
        capabilities = payload["capabilities"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        blockers.append(f"reference_capability_manifest_invalid:{exc}")
        capabilities = {}

    expected = {
        "reference_materials_elements_cpu": "structural_elements",
        "dense_assembly_cpu": "structural_assembly",
    }
    for capability, owner in expected.items():
        row = capabilities.get(capability, {})
        if row.get("status") != "implemented":
            blockers.append(f"reference_capability_not_implemented:{capability}")
        if row.get("cutover_gate") != "C1":
            blockers.append(f"reference_capability_gate_not_c1:{capability}")
        if row.get("owner") != owner:
            blockers.append(f"reference_capability_owner_invalid:{capability}")
        claim = str(row.get("claim", ""))
        for token in ("NumPy", "HIP C2", "C6"):
            if token not in claim:
                blockers.append(
                    f"reference_capability_scope_token_missing:{capability}:{token}"
                )
        if capability == "dense_assembly_cpu":
            for token in ("ABI v1.13", "ABI v1.14", "C3 integration candidate"):
                if token not in claim:
                    blockers.append(
                        f"reference_capability_scope_token_missing:{capability}:{token}"
                    )

    for relative, tokens in REQUIRED_TOKENS.items():
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"reference_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(f"reference_evidence_token_missing:{relative}:{token}")

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-reference-elements-contract.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "cutover_gate": "C1" if not blockers else None,
        "blockers": blockers,
        "claim_boundary": (
            "This is bounded CPU reference C1 evidence with an ABI/Rust C3 integration "
            "candidate. It does not close HIP C2, sequential C3 promotion, general "
            "elements/assembly, broader product E2E, or C6; the bounded typed-ModelIR "
            "linear C4/C5 composition is checked separately."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_native_reference_elements(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"Native reference materials/elements/assembly contract: {report['status']}"
        )
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
