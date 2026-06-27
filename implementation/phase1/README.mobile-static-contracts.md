# Phase1 mobile/static contract anchors

This README supplement is a mobile-editable anchor list for the static contracts added in PR #40. It avoids runtime execution and gives future workstation/CI work a stable map from the Phase1 README surface to the contract files.

## Mobile/static scope

Primary handoff:

- [Mobile/static development contracts](mobile-static-contracts.md)
- [Step5 RCA summary schema](step5_rca_summary.schema.json)
- [Step5 RCA static validation helper](step5_rca_contract.py)
- [Mobile-web dev-only backlog](mobile-web-dev-only-backlog.md)

Allowed from mobile/static environments:

- Markdown, JSON schema, small helper constants, docstrings, and reason-code tables
- Producer command templates and environment variable matrices
- Claim-boundary and next-action documentation

Not claimed from mobile/static environments:

- Python/Rust/HIP/npm/Playwright execution
- GitHub Actions or release-gate closure
- Protected evidence regeneration
- Solver, benchmark, customer-shadow, or strict HIP readiness promotion

## A1 anchor: LF -> GNN residual-correction contract

Files:

- [LF -> GNN smoke runner](lf_to_gnn_e2e_smoke.py)
- [GNN residual model compatibility module](gnn_residual_model.py)
- [Mobile/static LF -> GNN contract](mobile-static-contracts.md#A1-lf---gnn-interface-contract)

Required static vocabulary:

- `LF_GNN_REQUIRED_INPUT_FIELDS`
- `LF_GNN_OUTPUT_FIELDS`
- `LF_GNN_STANDARD_REASON_CODES`
- `CLAIM_BOUNDARY=residual_correction_assist_not_solver_truth`

The LF -> GNN path is an accelerator/reviewer-aid surface. It must not be used as autonomous solver truth until deterministic reference solver, residual/Jacobian/Newton closure, and benchmark truth are closed.

## A2 anchor: strict Rust/HIP producer handoff

Files:

- [Mobile/static strict Rust/HIP handoff](mobile-static-contracts.md#A2-strict-rusthip-producer-handoff)
- [Zero-copy strict probe schema and command handoff](mobile-static-contracts.md#command-template)

Static handoff command shape:

```bash
PHASE1_DISABLE_CPU_FALLBACK=1 \
python3 implementation/phase1/zero_copy_real_probe.py \
  --producer-cmd "<rust_or_hip_producer_command>" \
  --require-rust-hip \
  --out implementation/phase1/zero_copy_real_probe_report_strict.json
```

This anchor documents the handoff only. It does not prove that a strict Rust/HIP producer ran.

## A3 anchor: Step5 RCA summary schema

Files:

- [Step5 RCA summary schema](step5_rca_summary.schema.json)
- [Step5 RCA static validation helper](step5_rca_contract.py)
- [Mobile/static Step5 RCA contract](mobile-static-contracts.md#A3-step5-rca-summary-static-schema)

Required current gate fields:

```json
{
  "timing_breakdown_seconds": {
    "compute": 0.0,
    "host_copy": 0.0,
    "serialization": 0.0
  }
}
```

Recommended optional fields:

- `schema_version`
- `generated_at_utc`
- `run_id`
- `producer`
- `host_copy_share`
- `zero_copy_pass`
- `strict_probe_ref`
- `artifact_manifest`

Reason-code mapping:

| Condition | reason_code |
| --- | --- |
| Missing `timing_breakdown_seconds` or one of `compute`, `host_copy`, `serialization` | `ERR_MISSING_RCA_KEY` |
| Non-numeric, NaN, infinity, or negative timing value | `ERR_INVALID_RCA_VALUE` |
| `host_copy_share` outside `[0, 1]` | `ERR_INVALID_RCA_VALUE` |
| All static RCA fields satisfy the contract | `PASS` |

## Workstation/CI follow-up

1. Import or inline `validate_step5_rca_summary()` into `phase1_ci_gate.py::_validate_inputs()`.
2. Add tests that assert `missing_fields` and `invalid_fields` are preserved in the gate detail payload.
3. Run the existing Phase1 CI/test suite from a workstation or CI runner; do not infer pass status from this mobile/static PR.
