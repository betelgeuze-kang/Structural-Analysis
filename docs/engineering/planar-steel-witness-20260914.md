# Accepted steel witness at the 24 mm refinement discrepancy

A read-only audit of the retained 32/64-layer full displacement paths locates the
largest absolute plastic-strain difference at 24 mm in `E1:gauss-0:top`, integration
coordinate -0.7745966692414834. Path hashes and element/section/fiber bindings to
accepted checkpoints are checked before extracting observations. No solve or fit
is performed. The source files and the numerical 1% screen are unchanged.

Both models first record nonzero plastic strain at this steel point at the
sampled 24 mm target. At 22 mm both points remain elastic (about 229.1 MPa); at
24 mm both yield. Both paths have three yielded steel points at 24 mm, four at
26 mm and five at 28 mm. Thus the witness is not an elastic-versus-plastic label
mismatch at these sampled targets. The actual onset between sampled targets is
not resolved by this audit.

At 24 mm the witness plastic strains are 3.3769139705e-6 (32 layers) and
4.6690716599e-6 (64 layers), differing by 1.2921576894e-6. Total strains are
0.0012535119905 and 0.0012548558345; stresses are 250.0270153 and 250.0373526 MPa.
The full group's finer plastic-strain maximum is 8.5445592590e-5, which produced
the earlier 1.512258% group discrepancy. That percentage is a group-normalized
error, not the witness's own relative error.

This places the retained screen failure near the sampled onset of plasticity.
It does not prove a unique cause, establish exact quadrature error, or justify
loosening the screen. A subsequent reference calculation should preserve this
point and its full preceding history. Endpoint agreement must not erase it.

The audit records the same witness through all forty accepted targets. Packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-refinement-steel-witness-51u_bxxg`

Two payload files, 44,193 bytes; inventory SHA-256:
`e2e4f48a83d616ee6bdeb5991eaabda73a3da7818d4adff663e154a23c45768c`.
The retained `audit.py` checks source path identities and regenerates the audit.
No independent physical validation or training-reference qualification follows.

## Repository reproducer

The fixed-source audit is now available as
`scripts/audit_planar_steel_refinement_witness.py`. It accepts the two retained
path files at any filesystem location, verifies their fixed original SHA-256
identities before parsing, and writes the witness report to standard output.
It does not accept arbitrary model pairs or grant general geometry equivalence.
The immutable source pair and its documented model construction define its scope.

```sh
python3 scripts/audit_planar_steel_refinement_witness.py \
  /path/to/original-32-layer-path.json \
  /path/to/original-64-layer-path.json > witness.json
```

Source identities are `6d685a2e3d7e2b56bf21714705c2e543e94088c9da6c9e209e337cf34f81de65`
and `e552852440e2ff8d98cc23a1283550c3d2dacf09de528e87794fbef22cc48932`.
Even formatting-only changes fail source identity. The runtime checks use explicit
exceptions, not Python assertions, and verify the full accepted checkpoint chain,
forty targets, element/section/fiber bindings and unique steel observations.
No solver or trained model is imported.

Six focused synthetic integrity tests pass, covering identity-before-decode,
formatting-only identity changes, valid positional extraction, uncommitted trials,
steel-state mismatch and duplicate observations. They are input-boundary tests,
not structural benchmarks. Ruff checks pass for the script and tests.

An actual invocation on the retained 32/64-layer files reproduces the original
witness, first nonzero plastic targets and all forty observation rows exactly.
No new structural solves or fits occurred. The executable snapshot and resulting
report are retained at:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-portable-steel-audit-93o530hu`

Inventory SHA-256:
`2a13f242a541ced8da233d8d53ed891e211c919cbbb3426a8bad9648c56f28d9`.
The existing 1.512258% numerical discrepancy and qualification boundaries remain.
