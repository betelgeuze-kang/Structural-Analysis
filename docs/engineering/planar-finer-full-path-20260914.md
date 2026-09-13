# Full load path with refined concrete quadrature

Following the 32-to-64 accepted-prefix comparison, this run restores the original
four proportional load targets (0.25, 0.5, 0.75, 1.0). Both discretizations fail
at 1.0. Refining the section alone therefore did not complete this load path.

The frozen source is `3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`.
The research-only construction, verified source/input identities and exact
32-layer reconstruction follow `planar-finer-reference-20260914.md`.
The 64-layer model is constructed through the low-level section builder; the
public API remains capped at 32 layers. Both paths retain dense solution,
residual tolerance 1e-10, increment tolerance 1e-12, maximum 40 iterations and
the original six line-search factors. No fallback or regularization was added.

| Observation | 32 layers | 64 layers |
| --- | ---: | ---: |
| Committed targets | 3 | 3 |
| Last accepted factor | 0.75 | 0.75 |
| Failed target | 1.0 | 1.0 |
| Failed relative residual | 0.110638095 | 0.089272024 |
| Full-path convergence-history rows | 27 | 26 |
| Full-path line-search attempts | 37 | 39 |
| Single-observation path time | 13.474572 s | 23.659872 s |

Both terminal reasons are `line_search_failed_to_reduce_residual`. Each first
three steps exactly reproduces its separately preserved accepted-prefix path.
The failed step preserves the parent checkpoint exactly: parent, returned
accepted checkpoint and final path checkpoint equal the earlier factor-0.75
checkpoint. Both residual gates and overall contracts fail. Failed speed ratios
are null. History rows and line-search attempts are named work counters, not a
complete accounting of all assembly or serialization costs.

These residuals are far above the unchanged tolerance, so this observation does
not support relaxing a near-roundoff acceptance gate. It also does not establish
physical capacity or prove no equilibrium exists at factor 1.0. A subsequent
investigation should examine the refined model's failed direction and material
branches or an explicitly different continuation strategy; it should not
attribute this failure solely to the original coarse two-layer quadrature.
No training or independent physical validation was performed.

Durable packet with frozen protocol, runner, auditor, both full paths and
summaries:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-finer-full-path-hil7hqbq`

Seven payload files, 58,747,682 bytes; inventory SHA-256:
`aaf9e70e308bc082e8ee5d331398faf5284a8e4830d65123c47bec56090c44d0`.
The retained `run.py` creates a fresh packet and records its path in
`/tmp/structural-planar-finer-full-path-root.txt`; `audit.py` verifies path hashes,
exact prefix reproduction and rollback. Machine-readable results are in
`planar-finer-full-path-20260914.summary.json`.
