#!/usr/bin/env python3
"""Verify the bounded C5 single-host native durable-job evidence contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOKENS = {
    "native/crates/structural-runtime/src/job.rs": (
        "append_only_hash_chain_single_host.v1",
        "pub fn submit(",
        "pub fn claim_next(",
        "pub fn request_cancel(",
        "pub fn recover_expired_leases(",
        "finish_nonlinear_ndtha_product",
        "lock_exclusive",
        "job_completion_projection_mismatch",
    ),
    "native/crates/structural-runtime/tests/durable_job.rs": (
        "checkpointed_job_reopens_resumes_and_publishes_exact_terminal_artifacts",
        "expired_lease_recovers_after_reopen_and_stale_worker_is_rejected",
        "queued_and_running_cancellation_are_durable_and_idempotent",
        "concurrent_claim_has_one_winner_and_corrupt_blob_does_not_advance_state",
    ),
    "native/crates/structural-cli/src/job.rs": (
        "execute_next_durable_job",
        "export_durable_job",
        "job_cancel_pending",
        "job-receipt.json",
    ),
    "native/crates/structural-cli/tests/durable_job_cli.rs": (
        "clean_environment_submit_poll_checkpoint_resume_and_export_match_direct_run",
        "command.env_clear()",
        "durable/direct drift",
        "public_cancel_is_terminal_and_cannot_be_claimed",
    ),
    "docs/native/durable-job-runtime-v1.md": (
        "C5 only",
        "single-host",
        "HIP C2",
        "distributed consensus",
        "C6 Python removal",
    ),
}


def check_durable_job_contract(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    try:
        payload = json.loads(
            (root / "native/capabilities.json").read_text(encoding="utf-8")
        )
        row = payload["capabilities"]["durable_jobs"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        blockers.append(f"durable_job_capability_manifest_invalid:{exc}")
        row = {}
    if row.get("status") != "implemented":
        blockers.append("durable_job_capability_not_implemented")
    if row.get("cutover_gate") != "C5":
        blockers.append("durable_job_capability_gate_not_c5")
    if row.get("owner") != "structural-runtime":
        blockers.append("durable_job_capability_owner_invalid")
    claim = str(row.get("claim", ""))
    for token in (
        "bounded single-host CPU nonlinear-NDTHA",
        "append-only self-hashed event chains",
        "expired-lease crash reconciliation",
        "no Python or Node",
        "tenant authorization",
        "HIP C2",
        "C6",
    ):
        if token not in claim:
            blockers.append(f"durable_job_scope_token_missing:{token}")

    for relative, tokens in REQUIRED_TOKENS.items():
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"durable_job_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(
                    f"durable_job_evidence_token_missing:{relative}:{token}"
                )

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-bounded-durable-job-contract.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "cutover_gate": row.get("cutover_gate"),
        "blockers": blockers,
        "claim_boundary": (
            "This validates the bounded single-host CPU durable-job implementation evidence; "
            "it is not HIP, distributed-service, authorization, or C6 evidence."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_durable_job_contract(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native durable-job contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
