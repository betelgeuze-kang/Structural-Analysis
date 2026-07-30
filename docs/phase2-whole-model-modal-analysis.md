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
- The public wrapper derives the common source-bound 6DOF characteristic
  length and applies the symmetric coordinate transform `C^T K C` and
  `C^T M C`. Extracted vectors are recovered with `phi = C q` and residual,
  orthogonality, matrix hashes, and result hashes are evaluated in the original
  physical coordinates.
- The result records the scaling hash and manifest plus exact scaled stiffness
  and mass condition numbers when the reduced system has at most 256 equations.
  Larger or singular systems report the diagnostic as unavailable.
- No diagonal regularization or fallback solver is permitted.
- An incomplete repeated-eigenvalue cluster fails closed.
- Dense execution is capped at 512 free DOFs. Sparse extraction and binary
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
  `sha256:0fb654e00cdf73715a44ac09d63ec808fe589287988ee686921b70ecddcb6902`
- source-set:
  `sha256:787ac759ce7c9bb8b680e9f307522fb9a6bdf3be7bb21112875f40a5b0d2f812`

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
nonstructural lumped mass, response-spectrum or time-history analysis, sparse
modal extraction, production-scale binary mode-vector artifacts, ROCm/HIP modal
parity, general or mixed-stress whole-model buckling beyond the separate bounded
compression-frame receipt, a broad independent modal corpus beyond the separate
one-frame OpenSees technical comparison, Verification Level 2, commercial
equivalence, or release readiness.

The source-bound package at
`artifacts/vv/bounded_planar_external_modal_buckling_case_package/` now prepares
exact free-free rigid-mode and symmetric repeated-mode external cases. It records
no execution credit by itself. Separate current-source receipts now bind fresh
OpenSees modal and CalculiX buckling execution, while the same-operator
supplemental receipt supplies the packaged rigid/repeated-mode and portal rows.
Those exact matrix rows are therefore `fresh_external_technical`; the package
alone still cannot claim external execution or Level 2 authority.
