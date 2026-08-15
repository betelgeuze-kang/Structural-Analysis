#!/usr/bin/env python3
"""Verify typed-ModelIR linear C4/C5 composition without promoting numerical C2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOKENS = {
    "native/crates/structural-contracts/src/model_linear_product.rs": (
        "structural-model-ir-linear-analysis-request.v1",
        "decode_json_strict",
        "deny_unknown_fields",
        "model_identity",
        "SparseLinearConfigV1",
    ),
    "native/crates/structural-ffi/src/lib.rs": (
        "assemble_linear_zero_state",
        "linear_assembly_sizes",
        "linear_assembly_counts",
        "assemble_linear_reference",
        "SA_ABI_V1_13",
    ),
    "native/crates/structural-runtime/src/model_linear_checkpoint.rs": (
        'b"SAMLPC01"',
        "structural-model-ir-linear-checkpoint.v1",
        "ModelIrLinearCheckpointBindingsV1",
        "SparseLinearCheckpointV1::from_bytes",
        "CHECKPOINT_MISMATCH",
    ),
    "native/crates/structural-runtime/src/model_linear_product.rs": (
        "prepare_model_ir_linear_product",
        "recover_model_ir_linear_product",
        "recover_model_ir_linear_product_artifacts",
        "build_model_ir_linear_reaction_result_ir_v1",
        "generated_sparse_request",
        "structural-model-ir-linear-assembly-receipt.v1",
        "structural-model-ir-linear-result-recovery-ir.v1",
    ),
    "native/crates/structural-runtime/src/lib.rs": (
        "assemble_model_ir_linear",
        "assemble_model_ir_linear_state",
        "validate_model_ir_linear_product_sizes",
        "Api::load_model_ir_linear_assembly",
    ),
    "native/crates/structural-cli/src/model_linear_product.rs": (
        "execute_model_ir_linear_analysis",
        "publish_model_ir_linear_analysis",
        "prepare_model_ir_linear_product",
        "recover_model_ir_linear_product",
        "checkpoint.mlpcp",
        "result-recovery-ir.json",
        "reaction-result-ir.json",
        "receipt_hash",
    ),
    "native/crates/structural-cli/src/main.rs": (
        '"model-linear-run"',
        '"model-linear-resume"',
        '"--iteration-budget"',
        "read_bounded_regular_file",
    ),
    "native/crates/structural-cli/tests/model_ir_linear_product_cli.rs": (
        "bounded_two_pattern_combination_executes_and_restarts_exactly",
        "bounded_three_pattern_direct_combination_executes_and_restarts_exactly",
        "bounded_nested_combination_executes_and_restarts_exactly",
        "clean_environment_direct_and_real_iteration_resume_are_byte_identical",
        "every_checkpoint_byte_and_request_drift_fail_before_resume",
        "numerical_failure_publishes_both_terminal_checkpoints_without_result_files",
        "symlink_and_existing_destination_fail_without_partial_publication",
        '"reaction-result-ir.json"',
        "command.env_clear()",
        'command.env("PATH", "/nonexistent")',
    ),
    "native/tests/fixtures/model_ir_linear/frame_cantilever_weak_request.json": (
        "structural-model-ir-linear-analysis-request.v1",
        "sha256:43dfd7770d69075bc8f10ee6a7f903d6d66e39cf5d845eea78b976d04adb1610",
        '"load_pattern_id": "LC_WEAK"',
    ),
    "docs/native/modelir-linear-product-e2e-v1.md": (
        "C4",
        "C5",
        "SAMLPC01",
        "model-linear-run",
        "model-linear-resume",
        "Python/Node",
        "protected-runner HIP C2",
        "5,000,000 structural entries",
        "append-only ABI v1.14",
        "constrained-reaction ResultIR",
        "15 terminal files",
        "nonzero prescribed",
        "C6",
    ),
}


def _capability(
    payload: dict[str, object],
    capability: str,
    gate: str,
    owner: str,
    claim_tokens: tuple[str, ...],
    blockers: list[str],
) -> dict[str, object]:
    try:
        row = payload["capabilities"][capability]  # type: ignore[index]
    except (KeyError, TypeError):
        blockers.append(f"{capability}_capability_manifest_invalid")
        return {}
    if not isinstance(row, dict):
        blockers.append(f"{capability}_capability_manifest_invalid")
        return {}
    if row.get("status") != "implemented":
        blockers.append(f"{capability}_capability_not_implemented")
    if row.get("cutover_gate") != gate:
        blockers.append(f"{capability}_capability_gate_not_{gate.lower()}")
    if row.get("owner") != owner:
        blockers.append(f"{capability}_capability_owner_invalid")
    claim = str(row.get("claim", ""))
    for token in claim_tokens:
        if token not in claim:
            blockers.append(f"{capability}_scope_token_missing:{token}")
    return row


def check_model_ir_linear_product(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    try:
        payload = json.loads(
            (root / "native/capabilities.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        blockers.append(f"model_ir_linear_product_manifest_invalid:{exc}")
        payload = {}

    checkpoint = _capability(
        payload,
        "modelir_linear_checkpoint",
        "C4",
        "structural-runtime",
        (
            "bounded typed-ModelIR frame3d/truss3d CPU",
            "ABI v1.13 assembly",
            "ABI v1.10 real PCG iteration state",
            "every single-byte mutation",
            "protected-runner HIP C2",
            "C6",
        ),
        blockers,
    )
    product = _capability(
        payload,
        "modelir_linear_product_e2e",
        "C5",
        "structural-cli",
        (
            "model-linear-run/model-linear-resume",
            "ResultIR/ReportIR/Markdown",
            "active-DOF plus element recovery",
            "constrained-reaction ResultIR",
            "15-artifact directories",
            "no Python or Node",
            "protected-runner HIP C2",
            "C6",
        ),
        blockers,
    )
    reactions = _capability(
        payload,
        "modelir_linear_reaction_results",
        "C5",
        "structural-contracts",
        (
            "ABI v1.14",
            "internal-minus-external reaction",
            "canonical self-hashed reaction ResultIR",
            "approved protected-runner HIP C2",
            "C6",
        ),
        blockers,
    )
    try:
        dense = payload["capabilities"]["dense_assembly_cpu"]  # type: ignore[index]
    except (KeyError, TypeError):
        blockers.append("dense_assembly_cpu_capability_manifest_invalid")
        dense = {}
    if not isinstance(dense, dict) or dense.get("cutover_gate") != "C1":
        blockers.append("dense_assembly_cpu_sequential_gate_not_c1")
    else:
        dense_claim = str(dense.get("claim", ""))
        for token in ("protected-runner", "sequential gate remains C1", "C4/C5"):
            if token not in dense_claim:
                blockers.append(f"dense_assembly_cpu_nonpromotion_token_missing:{token}")

    for relative, tokens in REQUIRED_TOKENS.items():
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"model_ir_linear_product_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(
                    f"model_ir_linear_product_evidence_token_missing:{relative}:{token}"
                )

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-model-ir-linear-product-contract.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "checkpoint_gate": checkpoint.get("cutover_gate"),
        "product_gate": product.get("cutover_gate"),
        "reaction_result_gate": reactions.get("cutover_gate"),
        "sequential_numerical_gate": dense.get("cutover_gate")
        if isinstance(dense, dict)
        else None,
        "blockers": blockers,
        "claim_boundary": (
            "C4/C5 are separate bounded typed-ModelIR CPU implementation capabilities. "
            "Assembly and sparse numerical authority remain sequentially at C1 until an "
            "approved protected-runner HIP C2 receipt exists; this check cannot promote C2, "
            "authoritative C3, or C6."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_model_ir_linear_product(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native ModelIR linear product contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
