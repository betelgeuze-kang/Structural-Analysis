# Phase1 mobile/static development contracts

This handoff records work that can be completed from a mobile web or low-resource environment without running Python, Rust, HIP, npm, Playwright, or CI. It is intentionally contract-first: it defines schemas, reason codes, command templates, and reviewable text surfaces so the next workstation/ROCm pass can execute the gates without guessing intent.

## Scope boundary

Allowed in mobile/static mode:

- edit Markdown, JSON schema, and small contract tables
- add docstrings or constants that do not require execution to review
- define required fields, optional fields, reason codes, and next actions
- prepare producer command templates and environment variable matrices
- update backlog/checklist text

Not allowed in mobile/static mode:

- run `python`, `cargo`, `npm`, Playwright, or GitHub Actions
- regenerate release artifacts or protected evidence
- claim solver, HIP, benchmark, customer-shadow, or release gate closure
- attach synthetic data as external benchmark/customer evidence

## A1. LF -> GNN interface contract

The residual-learning path remains an accelerator/reviewer-aid surface. It must not become the source of solver truth until the deterministic reference solver, residual/Jacobian/Newton closure, and benchmark truth are closed.

### Input payload

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `schema_version` | yes | string | Interface version. Recommended: `phase1.lf_to_gnn.v1`. |
| `case_id` | yes | string | Stable case identifier used in reports and error messages. |
| `source_model_ref` | yes | string | Path, checksum id, or artifact id for the canonical/LF source. |
| `node_features` | yes | array/object | Node feature matrix or named feature payload. Must be non-empty. |
| `edge_index` | yes | array/object | Graph connectivity. Must reference valid node rows. |
| `edge_features` | no | array/object | Optional member/link feature matrix. |
| `lf_outputs` | yes | object | Low-fidelity solver response, including displacement/force/residual fields available to the residual model. |
| `boundary_conditions` | yes | object | Support/dof/foundation/damping state used to build the graph. |
| `normalization` | yes | object | Unit and non-dimensionalization metadata. |
| `provenance` | yes | object | Source commit, input checksum, producer, and generated-at metadata. |
| `claim_boundary` | yes | string | Must state residual-correction/preview boundary, not autonomous truth. |

### Output payload

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `status` | yes | string | `ready`, `blocked`, or `review`. |
| `reason_code` | yes | string | Deterministic reason code from the table below. |
| `delta_u` | no | array/object | Predicted residual displacement correction. Present only when `status=ready` or `review`. |
| `corrected_state` | no | object | Optional `U_LF + delta_u` response envelope. |
| `residual_metrics` | yes | object | Equilibrium/residual summary for review. |
| `uncertainty` | no | object | Optional UQ/confidence fields. |
| `unsupported_features` | yes | array | Explicit unsupported feature list. Empty when no unsupported features are detected. |
| `warnings` | yes | array | Non-blocking review warnings. |

### LF -> GNN reason codes

| reason_code | Meaning | Mobile/static next action |
| --- | --- | --- |
| `PASS` | Input/output contract is satisfied. | Keep claim boundary visible. |
| `ERR_LF_GNN_FIELD_MISSING` | Required field is absent. | Add field to producer or mark unsupported explicitly. |
| `ERR_LF_GNN_TYPE` | Field exists but has wrong type. | Normalize JSON/tensor envelope before model handoff. |
| `ERR_LF_GNN_EMPTY_BATCH` | Node/edge/LF batch is empty. | Block prediction; do not synthesize placeholder response. |
| `ERR_LF_GNN_SHAPE_MISMATCH` | Node, edge, or LF response dimensions are inconsistent. | Fix adapter shape mapping before training/inference. |
| `ERR_LF_GNN_UNSUPPORTED_FEATURE` | Feature family is outside the residual model scope. | Route to deterministic solver/fallback and record unsupported feature. |
| `ERR_LF_GNN_CLAIM_BOUNDARY` | Output tries to claim autonomous solver truth. | Downgrade wording to residual-correction assist. |

## A2. Strict Rust/HIP producer handoff

Mobile/static work can prepare the command and evidence vocabulary, but it must not claim that the real producer was executed.

### Command template

```bash
PHASE1_DISABLE_CPU_FALLBACK=1 \
python3 implementation/phase1/zero_copy_real_probe.py \
  --producer-cmd "<rust_or_hip_producer_command>" \
  --require-rust-hip \
  --out implementation/phase1/zero_copy_real_probe_report_strict.json
```

Solver-wide HIP evidence should then consume the strict probe:

```bash
PHASE1_DISABLE_CPU_FALLBACK=1 \
python3 implementation/phase1/run_solver_hip_e2e_contract.py \
  --strict-probe implementation/phase1/zero_copy_real_probe_report_strict.json \
  --min-device-residency-ratio 1.0 \
  --out implementation/phase1/solver_hip_e2e_contract_report.json
```

### Environment matrix

| Variable | Mobile/static contract | Runtime expectation |
| --- | --- | --- |
| `PHASE1_DISABLE_CPU_FALLBACK` | Documented as required for strict mode. | `1/true/yes/on` blocks CPU fallback paths. |
| `PHASE1_FORCE_CPU_RUNTIME` | Documented as incompatible with strict HIP evidence. | Must be unset/false for strict GPU evidence. |
| `PHASE1_GPU_STATIC_SOLVER_MODE` | Optional mode selector. | `newton` should be preferred over closed-form shortcuts for production claims. |
| `ROCR_VISIBLE_DEVICES` / `HIP_VISIBLE_DEVICES` | Optional workstation selector. | Must be recorded in external run notes when used. |

### Evidence class matrix

| Evidence class | Producer executed | CPU fallback allowed | Release/product claim |
| --- | ---: | ---: | --- |
| `stub` | no | n/a | Contract shape only. No performance/solver claim. |
| `mock` | no real producer | n/a | Adapter smoke only. No HIP claim. |
| `report-only` | previous report consumed | no mutation | Review/handoff only unless freshness gate accepts it. |
| `real-producer` | yes | maybe | Runtime evidence, but not strict if CPU fallback is possible. |
| `strict-rust-hip` | yes | no | Candidate strict GPU evidence when residency/host-copy gates pass. |

### HIP next-action codes

| reason_code | Meaning | Next action |
| --- | --- | --- |
| `ERR_STRICT_PROBE_FAIL` | Strict zero-copy probe is not GPU-strict clean. | Re-run producer with CPU fallback disabled and inspect strict probe row failures. |
| `ERR_GPU_STRICT_FAIL` | CPU backend/required/fallback detected in GPU strict gate. | Remove fallback path from the measured lane or downgrade the claim. |
| `ERR_HOST_COPY_SHARE` | Host-copy share exceeds threshold. | Keep main loop device-resident or move copies outside the measured region. |
| `ERR_SOLVER_HIP_E2E_FAIL` | One or more solver paths failed solver-wide HIP contract. | Split failing path by static/NDTHA/track and attach row-level runtime telemetry. |
| `ERR_SOLVER_TRUTHFULNESS_FAIL` | Top-level solver truthfulness gate failed. | Fix surrogate/simplified runtime markers before product wording changes. |

## A3. Step5 RCA summary static schema

`implementation/phase1/step5_rca_summary.schema.json` is the mobile/static schema anchor. It intentionally requires only the current gate-critical timing fields while allowing optional provenance fields for stronger future receipts.

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

```json
{
  "schema_version": "phase1.step5_rca_summary.v1",
  "generated_at_utc": "2026-06-27T00:00:00Z",
  "run_id": "<stable-run-id>",
  "producer": "<script-or-tool>",
  "host_copy_share": 0.0,
  "zero_copy_pass": true,
  "strict_probe_ref": "implementation/phase1/zero_copy_real_probe_report_strict.json",
  "artifact_manifest": {
    "version": "v1",
    "source_commit": "<sha>",
    "input_checksum": "sha256:<...>"
  }
}
```

Static validation expectations:

- `compute`, `host_copy`, and `serialization` must be finite and non-negative.
- `host_copy_share`, when present, must be in `[0, 1]`.
- `generated_at_utc`, when present, must be UTC date-time shaped.
- Missing required timing fields should map to `ERR_MISSING_RCA_KEY`.
- Non-numeric, NaN, infinity, or negative timing values should map to `ERR_INVALID_RCA_VALUE`.

## Done in this mobile/static pass

- Added `implementation/phase1/step5_rca_summary.schema.json`.
- Added this static handoff contract for A1/A2/A3.
- Updated the mobile backlog progress section to point future workers at the schema and handoff contract.

## Deferred to workstation/CI

- No Python/Rust/HIP/npm commands were executed.
- No protected evidence was regenerated.
- No release, solver, benchmark, customer-shadow, or strict HIP claim was promoted.
