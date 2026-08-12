#!/usr/bin/env python3
"""Verify the bounded loopback native job-service API evidence contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOKENS = {
    "native/crates/structural-cli/src/service.rs": (
        "structural-native-job-http-api.v1",
        "job_api_non_loopback_bind_rejected",
        "job_api_duplicate_header",
        "job_api_transfer_encoding_rejected",
        "job_api_pipelining_rejected",
        "Cache-Control: no-store",
        "X-Content-Type-Options: nosniff",
        "load_native_job_api_credentials",
        "opened.dev() != metadata.dev()",
        '"/v1/worker/run-once"',
        '"result-ir"',
        '"report-ir"',
    ),
    "native/crates/structural-cli/tests/job_service_api_cli.rs": (
        "clean_environment_http_checkpoint_survives_process_kill_and_restarts_exactly",
        ".env_clear()",
        "first.kill()",
        "direct.result_ir_json()",
        "direct.report_ir_json()",
        "direct.checkpoint_bytes()",
        "queued_cancellation_is_exposed_without_worker_or_secret_disclosure",
        "assert_no_token_leak",
    ),
    "docs/native/job-service-api-v1.md": (
        "closes C5 only",
        "single-tenant",
        "kills the service process",
        "byte-identical",
        "TLS",
        "tenant isolation",
        "HIP C2",
        "C6",
    ),
}


def check_job_service_api_contract(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    try:
        payload = json.loads(
            (root / "native/capabilities.json").read_text(encoding="utf-8")
        )
        row = payload["capabilities"]["service_api"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        blockers.append(f"job_service_api_capability_manifest_invalid:{exc}")
        row = {}
    if row.get("status") != "implemented":
        blockers.append("job_service_api_capability_not_implemented")
    if row.get("cutover_gate") != "C5":
        blockers.append("job_service_api_capability_gate_not_c5")
    if row.get("owner") != "structural-cli":
        blockers.append("job_service_api_capability_owner_invalid")
    claim = str(row.get("claim", ""))
    for token in (
        "loopback single-host single-tenant",
        "distinct hashed client/worker bearer credentials",
        "process kill after checkpoint",
        "byte-identical to direct native execution",
        "TLS",
        "tenant isolation",
        "HIP C2",
        "C6",
    ):
        if token not in claim:
            blockers.append(f"job_service_api_scope_token_missing:{token}")

    for relative, tokens in REQUIRED_TOKENS.items():
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"job_service_api_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(
                    f"job_service_api_evidence_token_missing:{relative}:{token}"
                )

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-bounded-job-service-api-contract.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "cutover_gate": row.get("cutover_gate"),
        "blockers": blockers,
        "claim_boundary": (
            "This validates one loopback single-tenant static-role C5 API; it is not TLS, "
            "tenant-isolation, distributed-worker, HIP, broader-solver, or C6 evidence."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_job_service_api_contract(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native job-service API contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
