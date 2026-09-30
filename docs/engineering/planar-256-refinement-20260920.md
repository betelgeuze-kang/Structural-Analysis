# Frozen-source 256-layer full-history experiment

The [localized concrete differences](planar-concrete-localization-20260920.md)
justify measuring another layer resolution while keeping the material model,
load history, geometry and solver criteria unchanged. This is an actual fresh
256-layer run, not a transfer of accepted 128-layer material states. No retry or
parameter fitting is planned. It remains a research-only layer count and does
not extend the public bounded API or establish physical accuracy.

## Completed execution and actual 128/256 comparison

The single fresh 256-layer run completed all forty targets, with `status=ready`
and its internal numerical contract passing. The comparison verified every
accepted checkpoint transition and the original 128-layer prefix/suffix restart.
The original packets were not rewritten. All **400 nodal/steel group comparisons**
meet the unchanged exploratory 1% screen. The largest steel-history difference
is 0.0288211% at 24 mm; the largest steel-stress difference is 0.0190027% at 72 mm.
Maximum translation and rotation differences are 0.00137790% and 0.00319217%.

Concrete field agreement remains incomplete: **34 of 240 groups exceed 1%**,
comprising 33 tensile-damage targets and one compressive-damage target.

| Concrete field | Maximum 64/128 difference (prior) | Maximum 128/256 difference | New target |
| --- | ---: | ---: | ---: |
| Tensile history strain | 0.269504% | 0.167610% | 10 mm |
| Compressive history strain | 0.219462% | 0.125041% | 72 mm |
| Tensile damage | 12.330094% | 6.683062% | 78 mm |
| Compressive damage | 1.937147% | 1.017034% | 72 mm |
| Dissipated energy density | 1.108178% | 0.710241% | 26 mm |
| Stress | 1.698073% | 0.861804% | 72 mm |

These are maxima over different grid-pair comparisons; their witnesses can move.
They show reduced observed discrepancies, not a demonstrated asymptotic order or
continuum-error bound. At the new tensile maximum, E3/Gauss 0/coarse cell 101 is
the witness and six of 2,304 projected cells exceed the group screen. At the new
compression maximum, E3/Gauss 2/cell 14 is the witness and one cell exceeds it.
The local criterion is retained despite this localization. No mesh-independent
material-field accuracy or independent physical validation is established.

The solve took 605.696848 s; section reconstruction took 0.536133 s. The interval
from source verification through result hashing was 647.850922 s and excludes
summary/inventory output and the subsequent audit. This single refinement run
is not a speedup experiment. It retains more detailed material history and is
not proposed as a cheaper production model.

All 466 retained source/protocol/input/result files were checked for byte length
and SHA-256: 1,409,091,307 bytes, inventory SHA-256
`d01c2ac989adfca3365c2346df32bb610c99c3fbb8a018f2bc117418d6dcfe71`.
Full result SHA-256:
`ae168bdad5cc4d23f0b246df39b84b1b800458033fe4ba0c9f4acaed7d98b695`.

The separate comparison report and two auditor sources are retained at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-128-256-audit-x4mlzq4i`:
3 payload files, 1,062,346 bytes; inventory SHA-256
`ec9d5862af14215a180fb89dca6c0eb8c64e327d6c66054d2b296da3f5ac7b8c`.
The adjacent committed summary retains maxima, all failing target/field identities,
source hashes and the run's timing boundaries. The full separate report contains
all 640 comparisons and per-section damage localization.

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

## Initial execution state before completion

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

## Comparison implementation prepared during execution

`scripts/audit_planar_256_refinement.py` pins the frozen experiment protocol and
original prefix/suffix hashes, requires an explicit hash for the new full path,
checks forty accepted targets and exact restart correspondence, and compares the
original ten nodal/steel groups plus all six projected concrete fields. Original
normalizer floors and the 1% group-infinity screen remain unchanged. Damage fields
also retain section localization and group threshold-exceedance counts.

The new observer successfully decoded all fourteen hash-verified original
128-layer prefix steps, including 18 sections and 36 steel points per step.
Synthetic checks cover group cardinality, nonfinite/boolean values, norm floors,
local maxima, source/state bindings and response-versus-history field access.
The combined audit/workflow selection passed 40 tests in 1.84 s. This preflight does not
constitute a 128/256 comparison: the full 256-layer artifact is still required.

The fine-artifact reader allows up to 2 GiB, separately from the existing
1 GiB default, because the retained pretty-printed full material history doubles
its concrete sampling. This input-size allowance changes no numerical criterion.
The comparator creates a separate output with exclusive creation and performs no
structural solves, original packet rewrites, AI fitting or physical qualification.
