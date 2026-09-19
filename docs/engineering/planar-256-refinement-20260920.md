# Frozen-source 256-layer full-history experiment

The [localized concrete differences](planar-concrete-localization-20260920.md)
justify measuring another layer resolution while keeping the material model,
load history, geometry and solver criteria unchanged. This is an actual fresh
256-layer run, not a transfer of accepted 128-layer material states. No retry or
parameter fitting is planned. It remains a research-only layer count and does
not extend the public bounded API or establish physical accuracy.

## Frozen protocol

- Original numerical source: `3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`.
- All 461 archived source files verified against the fixed manifest and actual
  Git blobs, then copied into the new experiment directory before import.
- Original source manifest SHA-256:
  `5cebb7cfcb4dce2228e59fd2006d198bc27afc7e6ad567cf2621d6fbc4d54b6a`.
- Canonical 32-layer input SHA-256:
  `34822feaee8f569712b46e5842f5fcc3253a9a851bb9a13c92624be238b4c23e`.
- Reconstruct the original sections exactly, replace only concrete layer count
  with 256, and verify unchanged outer steel fibers.
- Forty targets: 2, 4, ..., 80 mm; N6 UX, global DOF 15. Preserve the original
  proportional force vector. This does not represent constant axial loading.
- Dense NumPy solve, residual tolerance 1e-10; displacement control, increment
  and load-factor increment tolerances 1e-12; maximum 40 iterations; six unchanged
  line-search factors from 1 through 1/32. Coordinate scale remains 0.001 m.
- One observation. No statistical runtime or speedup conclusion. Measured setup,
  solve and enclosing-through-artifact-hash intervals exclude subsequent audit.

The committed driver is `scripts/run_planar_256_refinement.py`. It rejects source
identity or Git mismatches before importing copied numerical code. Focused
localization/source-integrity tests passed **16 tests in 1.63 s**; these are
software checks, not independent solver evidence.

## Execution state and comparison still required

At this record's creation, the solver was confirmed live as process 111759
(unified shell session 80440), after writing the protocol and entering the
forty-target solve. No completed-path or convergence result was yet available.
Do not launch another copy solely because observation takes time; inspect that
handle or authoritative process state first.

New packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-256-full-refinement-vfqmfsjd`

Pre-solve protocol SHA-256:
`9f28f6fe758a6aebea9852bc2a48ec747479645b85db5153cbed540650de9e3a`.
The retained `runner.py` exactly matches the committed driver. Original 64/128
packets are unchanged. Upon terminal execution, inspect status and accepted
checkpoint chains before comparing with the original 128-layer prefix/suffix.
Retain original nodal/steel group norms and all six concrete projected fields,
including local maximum discrepancies and localization descriptors. A small
section mean cannot override the original exploratory 1% group-infinity screen.
No full-history agreement, material convergence or physical qualification is
claimed before those comparisons are actually performed.
