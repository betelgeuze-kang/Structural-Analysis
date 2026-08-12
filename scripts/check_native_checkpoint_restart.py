#!/usr/bin/env python3
"""Verify that the bounded C4 checkpoint claim is backed by implementation evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOKENS = {
    "native/cpp/include/structural/abi_v1.h": (
        "SA_ABI_V1_5",
        "SA_CAPABILITY_NONLINEAR_NDTHA_RESTART_CPU",
        "sa_nonlinear_ndtha_state_v1",
        "nonlinear_ndtha_advance",
    ),
    "native/crates/structural-ffi/src/lib.rs": (
        "load_nonlinear_ndtha_restart",
        "initial_nonlinear_ndtha_state",
        "advance_nonlinear_ndtha",
    ),
    "native/crates/structural-runtime/src/checkpoint.rs": (
        'b"SANDCP01"',
        'b"structural-ndtha-model.v1\\0"',
        'b"structural-ndtha-state.v1\\0"',
        'b"structural-ndtha-execution.v1\\0"',
        "MAX_ARTIFACT_BYTES",
        "MAX_VECTOR_VALUES",
        "create_new(true)",
        "file.sync_all()",
        "fs::rename",
        "directory.sync_all()",
    ),
    "native/crates/structural-runtime/tests/nonlinear_ndtha_checkpoint.rs": (
        "canonical_checkpoint_round_trip_and_durable_restart_are_bitwise_exact",
        "every_single_byte_mutation_of_the_frozen_checkpoint_is_rejected",
        "collapse_checkpoint_is_terminal_and_reload_idempotent",
        "sha256:65ac4cf6fa660cb50f3a86a27c42044a52612bd8c9782c11406cc51fb1bce87b",
        "sha256:5b91e2dab5ee3ed977a3d7fca0ea0c1944661c10ab0a3f17ec4a85bfef77aaac",
    ),
    "docs/native/checkpoint-restart-v1.md": (
        "SANDCP01",
        "C4",
        "HIP parity",
        "process-crash recovery",
    ),
}


def check_checkpoint_restart_contract(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    manifest_path = root / "native/capabilities.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        row = payload["capabilities"]["checkpoint_restart"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        blockers.append(f"checkpoint_capability_manifest_invalid:{exc}")
        row = {}
    if row.get("status") != "implemented":
        blockers.append("checkpoint_capability_not_implemented")
    if row.get("cutover_gate") != "C4":
        blockers.append("checkpoint_capability_gate_not_c4")
    if row.get("owner") != "structural-runtime":
        blockers.append("checkpoint_capability_owner_invalid")
    claim = str(row.get("claim", ""))
    for token in (
        "bounded CPU",
        "model, state and execution SHA-256",
        "job-state crash recovery",
        "HIP C2",
        "product E2E",
    ):
        if token not in claim:
            blockers.append(f"checkpoint_capability_scope_token_missing:{token}")

    for relative, tokens in REQUIRED_TOKENS.items():
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"checkpoint_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(f"checkpoint_evidence_token_missing:{relative}:{token}")

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-checkpoint-restart-contract.v1",
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
    report = check_checkpoint_restart_contract(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native checkpoint/restart contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
