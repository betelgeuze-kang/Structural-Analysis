#!/usr/bin/env python3
"""Verify bounded nonlinear-static Newton C4/C5 evidence without over-promoting C2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOKENS = {
    "native/cpp/include/structural/abi_v1.h": (
        "SA_ABI_V1_11",
        "SA_CAPABILITY_NONLINEAR_STATIC_RESTART_CPU",
        "sa_nonlinear_static_state_v1",
        "sa_nonlinear_static_begin_fn_v1",
        "sa_nonlinear_static_advance_fn_v1",
    ),
    "native/cpp/tests/solver_cpu/nonlinear_static_test.cpp": (
        "restart_boundaries_are_complete_and_bitwise_stable",
        "advance_nonlinear_static",
    ),
    "native/cpp/tests/abi/nonlinear_static_contract_test.cpp": (
        "v1_11_restart_is_append_only_complete_and_failure_atomic",
        "SA_API_V1_10_MIN_SIZE",
        "SA_API_V1_11_MIN_SIZE",
        "SA_ERR_CHECKPOINT_MISMATCH",
    ),
    "native/crates/structural-ffi/tests/nonlinear_static_restart.rs": (
        "safe_v1_11_restart_is_bitwise_identical_across_real_newton_boundaries",
        "safe_v1_11_restart_rejects_tamper_and_binding_changes_atomically",
        "numerical_nonconvergence_remains_a_terminal_checkpoint_state",
        "v1_10_table_cannot_expose_v1_11_restart",
        "serde_json::to_vec",
    ),
    "native/crates/structural-contracts/src/static_product.rs": (
        "structural-nonlinear-static-request.v1",
        "structural-nonlinear-static-result-ir.v1",
        "structural-nonlinear-static-report-ir.v1",
        "nonlinear_static_model_hash_v1",
        "nonlinear_static_execution_hash_v1",
        "static_result_recovery_invalid",
    ),
    "native/crates/structural-contracts/tests/nonlinear_static_product_wire.rs": (
        "request_result_and_report_are_canonical_self_hashed_and_bound",
        "duplicate_unknown_nonfinite_dimension_and_recovery_drift_fail_closed",
    ),
    "native/crates/structural-runtime/src/static_checkpoint.rs": (
        'b"SASTAC01"',
        "structural-nonlinear-static-newton-state.v1",
        "structural-nonlinear-static-checkpoint.v1",
        "CHECKPOINT_MISMATCH",
        "encode_state",
        "decode_state",
    ),
    "native/crates/structural-runtime/src/lib.rs": (
        "advance_nonlinear_static_product",
        "checkpoint_nonlinear_static",
        "restore_nonlinear_static",
        "build_nonlinear_static_result_ir_v1",
    ),
    "native/crates/structural-runtime/tests/nonlinear_static_checkpoint_product.rs": (
        "real_iteration_checkpoint_resume_is_byte_identical_to_direct_completion",
        "every_single_byte_mutation_and_request_drift_fail_closed",
        "nonconvergence_is_terminal_and_checkpointable_without_result_ir",
    ),
    "native/crates/structural-report/src/lib.rs": (
        "build_nonlinear_static_report_v1",
        "bounded_candidate",
    ),
    "native/crates/structural-cli/src/static_product.rs": (
        "execute_nonlinear_static_analysis",
        "publish_nonlinear_static_analysis",
        "checkpoint.stacp",
        "receipt_hash",
    ),
    "native/crates/structural-cli/src/main.rs": (
        '"static-run"',
        '"static-resume"',
        '"--iteration-budget"',
    ),
    "native/crates/structural-cli/tests/nonlinear_static_product_cli.rs": (
        "python_node_free_direct_and_real_newton_resume_are_byte_identical",
        "command.env_clear()",
        "numerical_failure_publishes_terminal_checkpoint_and_returns_failure",
        "tamper_symlink_and_existing_destination_fail_without_publication",
    ),
    "docs/native/nonlinear-static-product-e2e-v1.md": (
        "C4",
        "C5",
        "SASTAC01",
        "real Newton iteration",
        "Python/Node",
        "HIP C2",
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


def check_nonlinear_static_product(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    try:
        payload = json.loads(
            (root / "native/capabilities.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        blockers.append(f"nonlinear_static_product_manifest_invalid:{exc}")
        payload = {}

    checkpoint = _check_capability(
        payload,
        "nonlinear_static_checkpoint",
        "C4",
        "structural-runtime",
        (
            "bounded story-frame CPU Newton",
            "ABI v1.11",
            "real iteration state",
            "model, Newton state, execution",
            "HIP C2",
            "C6",
        ),
        blockers,
    )
    product = _check_capability(
        payload,
        "nonlinear_static_product_e2e",
        "C5",
        "structural-cli",
        (
            "bounded story-frame CPU Newton",
            "ResultIR, ReportIR",
            "static-run/static-resume",
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
            blockers.append(f"nonlinear_static_product_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(
                    f"nonlinear_static_product_evidence_token_missing:{relative}:{token}"
                )

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-nonlinear-static-product-contract.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "checkpoint_gate": checkpoint.get("cutover_gate"),
        "product_gate": product.get("cutover_gate"),
        "sequential_numerical_gate": "C1",
        "blockers": blockers,
        "claim_boundary": (
            "C4/C5 are bounded story-frame CPU implementation capabilities. The nonlinear-"
            "static numerical family remains sequentially at C1 until an approved HIP C2 "
            "receipt exists; this check cannot promote C2 or C6."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_nonlinear_static_product(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native nonlinear-static product contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
