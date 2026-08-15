#!/usr/bin/env python3
"""Verify bounded typed-ModelIR linear durable-job/service C5 evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOKENS = {
    "native/crates/structural-contracts/src/model_linear_job.rs": (
        "structural-model-ir-linear-durable-job-request.v1",
        "model_ir_linear_cpu_v1",
        "decode_json_strict",
        "MODEL_IR_LINEAR_MAXIMUM_MODEL_BYTES",
        "MODEL_IR_LINEAR_MAXIMUM_JOB_REQUEST_BYTES",
        "model_ir_linear_job_model_identity_mismatch",
    ),
    "native/crates/structural-runtime/src/job.rs": (
        "DurableJobAnalysisProfileV1",
        "submit_model_ir_linear_envelope",
        "publish_model_ir_linear_checkpoint",
        "fail_model_ir_linear_job",
        "complete_model_ir_linear_job",
        "read_result_recovery_ir",
        "read_reaction_result_ir",
        "reaction_result_ir_bytes",
        "job_completion_projection_mismatch",
        "finish_sparse_linear_product",
    ),
    "native/crates/structural-runtime/tests/model_ir_linear_durable_job.rs": (
        "model_linear_job_reopens_resumes_and_revalidates_every_terminal_projection",
        "forged recovery rejected",
        "forged reactions rejected",
        "model_linear_numerical_failure_and_cooperative_cancel_retain_exact_checkpoints",
        "model_linear_expired_lease_requeues_after_reopen_and_rejects_stale_worker",
    ),
    "native/crates/structural-runtime/tests/durable_job.rs": (
        "expired_lease_recovers_after_reopen_and_stale_worker_is_rejected",
        '!submitted_event.contains("analysis_profile")',
        '!submitted_event.contains("result_recovery_ir")',
    ),
    "native/crates/structural-cli/src/job.rs": (
        "advance_model_ir_linear_job",
        "execute_model_ir_linear_analysis",
        "complete_model_ir_linear_job",
        "result-recovery-ir.json",
        "reaction-result-ir.json",
        "single_host_bounded_cpu_model_ir_linear_durable_job_export",
    ),
    "native/crates/structural-cli/src/job_cli.rs": (
        '"submit-model-linear"',
        "read_bounded_regular_file",
        "libc::O_NOFOLLOW",
        "MetadataExt",
        "submit_model_ir_linear",
    ),
    "native/crates/structural-cli/tests/model_ir_linear_durable_job_cli.rs": (
        "clean_process_job_restart_and_export_match_direct_model_product",
        "command.env_clear()",
        'command.env("PATH", "/nonexistent")',
        "artifact drift",
        '"reaction-result-ir.json"',
        "model_job_submit_rejects_symlink_input_without_store_creation",
    ),
    "native/crates/structural-cli/src/service.rs": (
        '"/v1/model-linear-jobs"',
        '"result-recovery-ir"',
        '"reaction-result-ir"',
        "submit_model_ir_linear_envelope",
        "MODEL_IR_LINEAR_MAXIMUM_JOB_REQUEST_BYTES",
        "execute_next_durable_job",
    ),
    "docs/native/modelir-linear-durable-job-v1.md": (
        "append-only, self-hashed",
        "expired lease",
        "submit-model-linear",
        "/v1/model-linear-jobs",
        "result-recovery-ir",
        "reaction-result-ir",
        "six numerical/report artifacts",
        "legacy no-reaction claim",
        "no Python",
        "protected-runner HIP C2",
        "authoritative numerical C3",
        "C6",
    ),
}


def _capability(
    payload: dict[str, object],
    name: str,
    owner: str,
    tokens: tuple[str, ...],
    blockers: list[str],
) -> dict[str, object]:
    try:
        row = payload["capabilities"][name]  # type: ignore[index]
    except (KeyError, TypeError):
        blockers.append(f"{name}_capability_manifest_invalid")
        return {}
    if not isinstance(row, dict):
        blockers.append(f"{name}_capability_manifest_invalid")
        return {}
    if row.get("status") != "implemented":
        blockers.append(f"{name}_capability_not_implemented")
    if row.get("cutover_gate") != "C5":
        blockers.append(f"{name}_capability_gate_not_c5")
    if row.get("owner") != owner:
        blockers.append(f"{name}_capability_owner_invalid")
    claim = str(row.get("claim", ""))
    for token in tokens:
        if token not in claim:
            blockers.append(f"{name}_scope_token_missing:{token}")
    return row


def check_model_ir_linear_jobs(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    try:
        payload = json.loads(
            (root / "native/capabilities.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        blockers.append(f"model_ir_linear_jobs_manifest_invalid:{exc}")
        payload = {}

    durable = _capability(
        payload,
        "modelir_linear_durable_jobs",
        "structural-runtime",
        (
            "bounded typed-ModelIR frame3d/truss3d CPU linear durable-job",
            "append-only self-hashed event chain",
            "expired-lease reconciliation",
            "exact completion re-projection",
            "constrained-reaction ResultIR",
            "six artifacts",
            "legacy no-reaction claim",
            "no Python or Node",
            "approved protected-runner HIP C2",
            "C2/C3 authority",
            "C6",
        ),
        blockers,
    )
    service = _capability(
        payload,
        "modelir_linear_service_api",
        "structural-cli",
        (
            "loopback single-host single-tenant",
            "POST /v1/model-linear-jobs",
            "distinct hashed client/worker role credentials",
            "/v1/jobs/{job_id}/result-recovery-ir",
            "/v1/jobs/{job_id}/reaction-result-ir",
            "no Python or Node",
            "live process-kill evidence",
            "TLS",
            "tenant isolation",
            "approved protected-runner HIP C2",
            "C6",
        ),
        blockers,
    )

    numerical_gates: dict[str, object] = {}
    for name in ("dense_assembly_cpu", "sparse_linear_solver_cpu"):
        try:
            row = payload["capabilities"][name]  # type: ignore[index]
        except (KeyError, TypeError):
            blockers.append(f"{name}_capability_manifest_invalid")
            continue
        if not isinstance(row, dict) or row.get("cutover_gate") != "C1":
            blockers.append(f"{name}_sequential_gate_not_c1")
            continue
        numerical_gates[name] = row.get("cutover_gate")
        claim = str(row.get("claim", ""))
        for token in ("sequential gate remains C1", "protected-runner"):
            if token not in claim:
                blockers.append(f"{name}_nonpromotion_token_missing:{token}")

    for relative, tokens in REQUIRED_TOKENS.items():
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"model_ir_linear_jobs_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(
                    f"model_ir_linear_jobs_evidence_token_missing:{relative}:{token}"
                )

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-model-ir-linear-jobs-contract.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "durable_job_gate": durable.get("cutover_gate"),
        "service_api_gate": service.get("cutover_gate"),
        "sequential_numerical_gates": numerical_gates,
        "blockers": blockers,
        "claim_boundary": (
            "This check closes only bounded typed-ModelIR CPU durable-job and loopback-service "
            "C5 composition. It cannot promote numerical C2, authoritative C3, or C6."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_model_ir_linear_jobs(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native ModelIR linear jobs contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
