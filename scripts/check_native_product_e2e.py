#!/usr/bin/env python3
"""Verify that the bounded C5 native product claim has executable contract evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOKENS = {
    "native/crates/structural-contracts/src/product_ir.rs": (
        "structural-native-analysis-request.v1",
        "structural-native-nonlinear-ndtha-result-ir.v1",
        "structural-native-nonlinear-ndtha-report-ir.v1",
        "BoundedCandidate",
        "result_ir_hash_mismatch",
        "report_ir_hash_mismatch",
    ),
    "native/crates/structural-runtime/src/lib.rs": (
        "finish_nonlinear_ndtha_product",
        "Physical response channels are copied from the state already produced",
        "checkpoint_hash: receipt.checkpoint_hash",
    ),
    "native/crates/structural-report/src/lib.rs": (
        "build_nonlinear_ndtha_report_v1",
        "deterministic projection of a bounded candidate result",
    ),
    "native/crates/structural-cli/src/product.rs": (
        "execute_native_analysis",
        "publish_native_analysis",
        "create_new(true)",
        "fs::rename",
        "receipt_hash",
    ),
    "native/crates/structural-cli/src/main.rs": (
        '"analysis"',
        '"run"',
        '"resume"',
        '"--step-budget"',
        '"--output-dir"',
    ),
    "native/crates/structural-cli/tests/nonlinear_ndtha_product_cli.rs": (
        "python_and_node_free_cli_run_resume_are_bitwise_identical",
        "command.env_clear()",
        "artifact hash drift",
        "tampered_checkpoint_and_existing_destination_fail_without_publication",
        "sha256:c5463cf386dc720ba44baa04cccf02be7b7365a550b1b9fc577480204928acac",
    ),
    "docs/native/bounded-product-e2e-v1.md": (
        "C5",
        "bounded_candidate",
        "HIP C2",
        "durable job submit/poll/cancel/crash reconciliation",
        "C6",
    ),
}


def check_product_e2e_contract(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    try:
        payload = json.loads(
            (root / "native/capabilities.json").read_text(encoding="utf-8")
        )
        row = payload["capabilities"]["product_e2e"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        blockers.append(f"product_e2e_capability_manifest_invalid:{exc}")
        row = {}
    if row.get("status") != "implemented":
        blockers.append("product_e2e_capability_not_implemented")
    if row.get("cutover_gate") != "C5":
        blockers.append("product_e2e_capability_gate_not_c5")
    if row.get("owner") != "structural-cli":
        blockers.append("product_e2e_capability_owner_invalid")
    claim = str(row.get("claim", ""))
    for token in (
        "bounded CPU nonlinear-NDTHA",
        "ResultIR, ReportIR",
        "no Python or Node",
        "HIP C2",
        "durable jobs/API",
        "C6",
    ):
        if token not in claim:
            blockers.append(f"product_e2e_scope_token_missing:{token}")

    for relative, tokens in REQUIRED_TOKENS.items():
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"product_e2e_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(
                    f"product_e2e_evidence_token_missing:{relative}:{token}"
                )

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-bounded-product-e2e-contract.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "cutover_gate": row.get("cutover_gate"),
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_product_e2e_contract(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native bounded product E2E contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
