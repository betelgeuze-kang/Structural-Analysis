# Phase 2 bounded whole-model modal analysis

This slice connects the strict generalized-eigen modal kernel to the public
`load_model` / `analyze` API for a deliberately bounded 3D frame/truss path.
It assembles global elastic stiffness and element consistent mass, reduces the
matrices to active unconstrained DOFs, excludes rigid-body modes, and returns
frequencies, periods, small inline max-component-normalized mode shapes, and
UX/UY/UZ participation and effective modal mass.

## Numerical contract

- Canonical input units are `m` and `kN`.
- Material density must be explicit, finite, positive, and expressed in
  `kg/m3`; no default density is inferred.
- The mass matrix is stored in `kN*s2/m` and uses Euler-Bernoulli frame or
  translational truss consistent mass.
- The solver is `authoritative_cpu_modal_fea_3d_v1` with the strict
  `scipy_linalg_eigh_dense` generalized-eigen backend.
- No diagonal regularization or fallback solver is permitted.
- An incomplete repeated-eigenvalue cluster fails closed.
- Dense execution is capped at 512 free DOFs. An explicit experimental ARPACK
  sparse-extraction backend is available, but it still consumes matrices from
  dense whole-model assembly and is capped at 4,096 free DOFs. Binary
  large-mode vector artifacts are not silently substituted.
- Nodal, element-added, and nonstructural lumped mass inputs fail closed because
  those formulations are not connected yet.

The public result inlines only max-component-normalized shapes for this bounded
small-dense path. Each mass-normalized reduced mode is represented by a SHA-256;
the mass-normalized vector itself is not mislabeled as a connected binary vector
artifact.

## Source-bound verification gates

The committed receipt executes four cases through the public API:

| Gate | Truth basis | Recorded result |
| --- | --- | --- |
| Frame cantilever | One-element Euler-Bernoulli consistent-mass closed form | eigenvalues `79491.6697691323`, `7716686.674179917 rad2/s2`; two-mode UY cumulative effective mass ratio `1.0` |
| Truss axial bar | One-element axial consistent-mass closed form | eigenvalue `19108280.25477707 rad2/s2` |
| Free-free frame | 3D rigid-body invariant | exactly 6 rigid modes excluded and 6 positive modes returned |
| Symmetric bending cluster | Complete repeated-eigenspace invariant | `mode_count=1` blocked; `mode_count=2` ready with equal eigenvalues `79491.6697691323 rad2/s2` |

All four gates pass deterministic raw and semantic replay checks. The receipt is
still `status=partial` because passing this bounded slice does not establish the
broader product claims listed below.

Current bindings:

- result artifact:
  `sha256:d0effdfc1e269fcd169b5901a8187fcf8eb5a154dba2b12fc05767d8548be5ca`
- source-set:
  `sha256:545a38c7d97cd827351c9cd39f66573331839f43d46ea91bfb21fbad6415ecd9`

Artifacts:

- `implementation/phase1/release_evidence/productization/phase2_whole_model_modal_result.json`
- `implementation/phase1/release_evidence/productization/phase2_whole_model_modal_summary.json`
- `src/structural_analysis/schemas/whole_model_modal_v1.schema.json`

Run:

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_whole_model_modal_analysis.py \
  tests/test_build_phase2_whole_model_modal_artifacts.py
PYTHONPATH=src python3 scripts/build_phase2_whole_model_modal_artifacts.py
PYTHONPATH=src python3 scripts/build_phase2_whole_model_modal_artifacts.py --check
```

## Explicit non-claims

This evidence does not prove a general frame/shell modal workflow, nodal or
nonstructural lumped mass, response-spectrum or time-history analysis, native
sparse modal assembly, production-scale binary mode-vector artifacts, ROCm/HIP modal
parity, general or mixed-stress whole-model buckling beyond the separate bounded
compression-frame receipt, a broad independent modal corpus beyond the separate
one-frame OpenSees technical comparison, Verification Level 2, commercial
equivalence, or release readiness.

The non-promoting sparse extraction contract and invocation are documented in
`docs/sparse-modal-buckling.md`.
