#!/usr/bin/env python3
"""Verify bounded sparse-PCG C4/C5 product evidence without over-promoting C2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOKENS = {
    "native/cpp/include/structural/abi_v1.h": (
        "SA_ABI_V1_10",
        "SA_CAPABILITY_SPARSE_LINEAR_RESTART_CPU",
        "sa_sparse_linear_state_v1",
        "sa_sparse_linear_begin_fn_v1",
        "sa_sparse_linear_advance_fn_v1",
    ),
    "native/cpp/tests/abi/sparse_linear_contract_test.cpp": (
        "caller_owned_restart_is_complete_and_failure_atomic",
        "SA_API_V1_9_MIN_SIZE",
        "SA_API_V1_10_MIN_SIZE",
        "SA_ERR_CHECKPOINT_MISMATCH",
    ),
    "native/crates/structural-ffi/tests/sparse_linear_restart.rs": (
        "safe_v1_10_restart_is_bitwise_identical_across_real_pcg_boundaries",
        "safe_v1_10_restart_rejects_tamper_and_binding_changes_atomically",
        "numerical_outcomes_remain_terminal_checkpoint_states",
        "v1_9_table_cannot_expose_v1_10_restart",
        "serde_json::to_vec",
    ),
    "native/crates/structural-contracts/src/sparse_product.rs": (
        "structural-sparse-linear-request.v1",
        "structural-sparse-linear-result-ir.v1",
        "structural-sparse-linear-report-ir.v1",
        "sparse_linear_model_hash_v1",
        "sparse_linear_execution_hash_v1",
        "sparse_result_residual_invalid",
    ),
    "native/crates/structural-contracts/tests/sparse_product_wire.rs": (
        "request_is_strict_canonical_and_identity_stable",
        "result_and_report_are_self_hashed_and_bound_to_true_residual",
        "let duplicate =",
    ),
    "native/crates/structural-runtime/src/sparse_checkpoint.rs": (
        'b"SAPCGC01"',
        "structural-sparse-linear-pcg-state.v1",
        "structural-sparse-linear-checkpoint.v1",
        "CHECKPOINT_MISMATCH",
        "encode_state",
        "decode_state",
    ),
    "native/crates/structural-runtime/src/lib.rs": (
        "advance_sparse_linear_product",
        "checkpoint_sparse_linear",
        "restore_sparse_linear",
        "build_sparse_linear_result_ir_v1",
    ),
    "native/crates/structural-runtime/tests/sparse_linear_checkpoint_product.rs": (
        "checkpoint_round_trip_contains_the_actual_iteration_state_and_all_hashes",
        "every_checkpoint_byte_and_request_drift_fail_closed",
        "segmented_resume_and_direct_execution_publish_identical_terminal_artifacts",
        "numerical_failure_is_a_durable_terminal_checkpoint_not_lost_partial_state",
    ),
    "native/crates/structural-report/src/lib.rs": (
        "build_sparse_linear_report_v1",
        "bounded_candidate",
    ),
    "native/crates/structural-cli/src/sparse_product.rs": (
        "execute_sparse_linear_analysis",
        "publish_sparse_linear_analysis",
        "checkpoint.pcgcp",
        "receipt_hash",
    ),
    "native/crates/structural-cli/src/main.rs": (
        '"linear-run"',
        '"linear-resume"',
        '"--iteration-budget"',
    ),
    "native/crates/structural-cli/tests/sparse_linear_product_cli.rs": (
        "python_node_free_direct_and_real_iteration_resume_are_byte_identical",
        "command.env_clear()",
        "numerical_failure_publishes_terminal_checkpoint_and_returns_failure",
        "tamper_symlink_and_existing_destination_fail_without_publication",
    ),
    "docs/native/sparse-linear-product-e2e-v1.md": (
        "C4",
        "C5",
        "SAPCGC01",
        "real iteration",
        "Python/Node",
        "protected-runner C2",
        "C6",
    ),
}


def _check_capability(
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


def check_sparse_linear_product(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    try:
        payload = json.loads(
            (root / "native/capabilities.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        blockers.append(f"sparse_linear_product_manifest_invalid:{exc}")
        payload = {}

    checkpoint = _check_capability(
        payload,
        "sparse_linear_checkpoint",
        "C4",
        "structural-runtime",
        (
            "bounded canonical-CSR CPU",
            "ABI v1.10",
            "real iteration state",
            "model, iterative state, execution",
            "HIP C2",
            "C6",
        ),
        blockers,
    )
    product = _check_capability(
        payload,
        "sparse_linear_product_e2e",
        "C5",
        "structural-cli",
        (
            "bounded canonical-CSR CPU",
            "ResultIR, ReportIR",
            "linear-run/linear-resume",
            "no Python or Node",
            "HIP C2",
            "C6",
        ),
        blockers,
    )

    for relative, tokens in REQUIRED_TOKENS.items():
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"sparse_linear_product_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(
                    f"sparse_linear_product_evidence_token_missing:{relative}:{token}"
                )

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-sparse-linear-product-contract.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "checkpoint_gate": checkpoint.get("cutover_gate"),
        "product_gate": product.get("cutover_gate"),
        "sequential_numerical_gate": "C1",
        "blockers": blockers,
        "claim_boundary": (
            "C4/C5 are bounded canonical-CSR CPU implementation capabilities. The sparse "
            "numerical family remains sequentially at C1 until an approved protected-runner "
            "HIP C2 receipt exists; this check cannot promote C2 or C6."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_sparse_linear_product(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native sparse-linear product contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
