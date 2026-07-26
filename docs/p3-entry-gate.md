# P3 entry gate

P3 is **blocked**. This is a change-control result, not a missing checkbox that
local code can waive. The ordered roadmap permits P3 implementation and product
promotion only after P0-P2 numerical truth, both Level 2 solver slots, the P2
published/external evidence set, the durable job boundary, and a current
authoritative release snapshot are closed.

The machine-readable decision is
[`artifacts/manifests/p3_entry_gate.json`](../artifacts/manifests/p3_entry_gate.json).
It is generated and drift-checked by `scripts/build_p3_entry_gate.py`. A truthful
blocked decision has `contract_pass=true` and `entry_gate_pass=false`; the first
field validates the gate artifact, while the second denies P3 entry.

## Existing-asset classification

| Existing asset | Classification | Why it cannot be promoted to P3 |
| --- | --- | --- |
| `src/structural_analysis/assembly/coupled_static.py` | Two-DOF frame/shell-*named* nonlinear spring seed | It has no shell element, mesh assembly, integration-point state, or general mixed solve. |
| `implementation/phase1/run_mgt_coupled_frame_shell_sparse_equilibrium.py` | Large-model linear sparse technical probe | Its receipt explicitly keeps `coupled_frame_shell_nonlinear_equilibrium=false`. |
| phase1 shell/contact/SSI/stage scripts and surface reports | Research, proxy, or diagnostic evidence | They are outside the canonical core public boundary and do not carry a promoted solver profile or external V&V authority. |
| Engine-v2 HIP kernels and receipts | Bounded performance research | CPU sparse reference closure, full-path parity, device residency, no-fallback proof, hardware provenance, and external V&V are not jointly closed. |
| Design-optimization and KDS data assets | Optimization/research inputs | They do not implement or validate a public design-code authority module. |
| Customer-shadow intake/status assets | Evidence intake contract | The validated count is `0/3`; templates and intake packets are not customer evidence. |

The repository has no canonical-core public shell/plate, contact, cable, SSI,
staged-construction, mixed nonlinear frame-shell, distributed-execution, or
design-code capability. The capability registry therefore records every P3
family as `blocked`, `public=false`, and `authority=none`. Guarded AI execution
and ROCm/HIP production remain blocked as well.

## Gate semantics

P3 entry requires all of the following at the same committed current HEAD:

- P0, P1, and P2 are `closed`;
- ordered PR gates 1-18 are `closed`;
- the snapshot is authoritative and its overall closure gate passes;
- repository hygiene, legal approval, and committed CI evidence are closed;
- OpenSees and the second independent solver have promoted Level 2 packages;
- published material-cyclic and snap-through Level 3 receipts pass;
- the 3D frame external comparison and signed engineering review pass; and
- checkpoint/resume is promoted through the job-service product boundary.

After entry, P3 completion additionally requires every P3 capability to be
supported within an explicit profile and at least three validated completed-
project customer-shadow cases. Proxy, fallback, template, benchmark-bridge, or
repository-generated evidence never substitutes for those requirements.
