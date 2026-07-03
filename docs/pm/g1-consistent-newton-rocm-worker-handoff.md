# G1 Consistent Residual/Jacobian Newton ROCm Worker Handoff

> Status: **non-promoting CTO/PM execution handoff**  
> Scope: G1 next diagnostic and implementation lane  
> This handoff does **not** close G1, does not prove full-load 1.0, does not prove material Newton breadth, and does not prove production ROCm/HIP residency.

## 1. Current G1 route

The latest G1 cause-narrowing receipt routes the next G1 work away from row-only support / elastic-link correction and toward:

```text
consistent_residual_jacobian_newton_rocm_worker
```

Required receipts:

```text
implementation/phase1/release_evidence/productization/mgt_residual_jacobian_consistency_hip_required_probe.json
implementation/phase1/release_evidence/productization/g1_full_load_hip_newton_lane_report.json
```

The route is diagnostic and non-promoting until all closure gates pass.

## 2. Why row-only support/link work should stop

The current cause-narrowing evidence shows:

| Signal | Current value | Interpretation |
|---|---:|---|
| Dominant near-null rows | 64 | There is a real distributed near-null packet. |
| Direct support member count | 0/64 | Dominant rows are not direct support rows. |
| Direct elastic-link endpoint count | 0/64 | Dominant rows are not direct elastic-link endpoints. |
| Elastic-link reachable to support count | 0/64 | Elastic-link-only graph does not explain the path. |
| Element graph dominant nodes reachable to support | 8/8 | Full structural graph does connect dominant nodes to supports. |
| Element graph connectivity gap detected | false | A pure connectivity inventory fix is not the primary next lane. |
| F2H 0.1->0.2->0.4 | ready | Lightweight continuation exists as non-promoting context. |
| Residual trend over F2H | nondecreasing | Load-dependent tangent/softening remains diagnostically active. |

Decision:

```text
stop_support_or_elastic_link_row_only_loop
```

Accepted next lanes:

```text
consistent_residual_jacobian_newton_rocm_worker
load_dependent_near_null_geometric_stiffness_comparison
production_rocm_hip_residual_jvp_worker
```

## 3. Current hard blockers

### 3.1 Checkpoint / full-load blockers

| Gate | Current state |
|---|---|
| Highest observed load scale | `0.656` |
| Required full load | `1.0` |
| Gap to full load | `0.344` |
| Full-load candidate count | `0` |
| Selected checkpoint | retained 0.656 checkpoint |

### 3.2 Child direct-probe blockers

```text
child_consistent_residual_jacobian_newton_not_proven
child_direct_residual_gate_not_proven
child_direct_residual_newton_ready_not_proven
child_fallback_zero_not_proven
child_full_load_closure_not_proven
child_material_newton_breadth_not_proven
child_observed_load_scale_below_required_full_load
child_relative_increment_gate_not_proven
```

### 3.3 ROCm/HIP runtime blockers

```text
rocm_hip_runtime_unavailable
runtime::dev_kfd_missing
runtime::dev_dri_missing
```

### 3.4 Production ROCm/HIP residual/JVP worker blockers

```text
consistent_residual_jacobian_newton_gate_not_passed
current_tangent_residual_row_hip_replay_not_proven
direct_probe_not_executed
global_krylov_accepted_state_tangent_refresh_hip_not_proven
global_krylov_hip_solver_not_proven
global_krylov_jvp_rows_not_retained
production_hip_residual_jacobian_path_not_proven
rocm_hip_runtime_unavailable
runtime::dev_dri_missing
runtime::dev_kfd_missing
```

## 4. Execution goals

### Goal A — Runtime proof

Prove that the target machine has a valid ROCm/HIP execution interface.

Required checks:

```bash
ls -l /dev/kfd /dev/dri || true
python3 - <<'PY'
import torch
print('torch', torch.__version__)
print('hip', getattr(torch.version, 'hip', None))
print('cuda_is_available_api', torch.cuda.is_available())
if torch.cuda.is_available():
    print('device', torch.cuda.get_device_name(0))
PY
```

Acceptance:

```text
/dev/kfd present
/dev/dri present
ROCm/HIP runtime available
runtime_environment_pass=true
```

### Goal B — HIP-required residual/Jacobian consistency probe

Run the HIP-required residual/Jacobian consistency probe and persist a non-promoting receipt.

Target receipt:

```text
implementation/phase1/release_evidence/productization/mgt_residual_jacobian_consistency_hip_required_probe.json
```

Acceptance:

```text
status=ready
consistent_residual_jacobian_newton_gate_passed=true
physical residual and JVP use the same state/operator
regularized fixed-point residual is not counted as physical direct residual
no CPU fallback is counted as production HIP proof
```

### Goal C — Production ROCm/HIP residual/JVP worker proof

Target capabilities:

```text
production_hip_residual_jacobian_path_proven=true
current_tangent_residual_row_hip_replay_proven=true
global_krylov_accepted_state_tangent_refresh_hip_proven=true
global_krylov_hip_solver_proven=true
global_krylov_jvp_rows_retained=true
```

Acceptance:

```text
production_rocm_hip_residual_jvp_worker.ready=true
residual_jvp_worker_path_ready=true
no CPU fallback
JVP/residual residency proof attached
CPU/GPU parity checked after CPU reference gates
```

### Goal D — Full-load candidate generation remains separate

The HIP worker lane does not itself close full load. G1 still needs:

```text
full-load 1.0 checkpoint candidate
direct residual gate
relative increment gate
material Newton breadth
fallback-zero or fully traced degraded state
```

## 5. Required command skeleton

The exact commands depend on the current scripts and runtime host. Use the following sequence as the handoff skeleton:

```bash
# 1. Runtime preflight
python3 scripts/check_github_actions_self_hosted_runner_status.py --check --fail-blocked

# 2. HIP strict runtime/probe preflight, if available in the runtime checkout
PHASE1_DISABLE_CPU_FALLBACK=1 \
python3 implementation/phase1/zero_copy_real_probe.py \
  --producer-cmd "/usr/bin/python3 implementation/phase1/rust_hip_md3bead_hook.py" \
  --require-rust-hip \
  --out implementation/phase1/zero_copy_real_probe_report_strict.local.json

# 3. G1 residual/Jacobian consistency probe
python3 implementation/phase1/run_mgt_residual_jacobian_consistency_probe.py \
  --hip-required \
  --out implementation/phase1/release_evidence/productization/mgt_residual_jacobian_consistency_hip_required_probe.local.json

# 4. G1 full-load HIP/Newton lane report refresh
python3 scripts/run_g1_full_load_hip_newton_lane.py \
  --out implementation/phase1/release_evidence/productization/g1_full_load_hip_newton_lane_report.local.json
```

If a command writes `.local.json`, do not promote or commit it unless the repository policy explicitly allows that receipt to become tracked evidence.

## 6. Gate acceptance table

| Gate | Required before G1 promotion? | Current handoff goal |
|---|---:|---|
| ROCm/HIP runtime present | yes for HIP residency | Remove `/dev/kfd`, `/dev/dri`, runtime unavailable blockers. |
| Consistent residual/Jacobian Newton | yes | Make `consistent_residual_jacobian_newton_gate_passed=true`. |
| Production HIP residual/JVP worker | yes for production residency | Prove device-resident residual/JVP, no CPU fallback. |
| Full-load 1.0 checkpoint | yes | Generate candidate after worker/gate path is coherent. |
| Direct residual gate | yes | Keep separate from fixed-point residual. |
| Relative increment gate | yes | Must pass with direct residual gate. |
| Material Newton breadth | yes | Not closed by ROCm runtime proof. |
| External benchmark/customer evidence | commercial claim | Not part of G1 technical closure but required for commercial upgrade. |

## 7. Non-promoting guardrails

Do not claim any of the following from this lane alone:

```text
G1 closed
full-load 1.0 closed
full commercial replacement ready
material Newton breadth closed
CPU/GPU parity complete
production HIP residency complete
paid pilot ready
```

Rejected substitutes:

```text
non-promoting F2g/F2h diagnostic readiness
row-active residual frontier descent below full-load 1.0
CPU diagnostic direct residual proof counted as production HIP
HIP compatibility alias without device-resident residual/JVP proof
regularized fixed-point residual counted as physical direct residual
```

## 8. PM/CTO exit criteria

The next PM checkpoint should only mark this lane complete when:

```text
mgt_residual_jacobian_consistency_hip_required_probe.status == ready
g1_full_load_hip_newton_lane_report.contract_pass == true OR the report has fewer, better-partitioned blockers
production_rocm_hip_residual_jvp_worker.ready == true
consistent_residual_jacobian_newton_gate_passed == true
all remaining non-closure blockers are explicitly routed to full-load/material/external tracks
```
