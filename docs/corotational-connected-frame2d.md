# Connected Corotational Frame2D Candidate

`corotational_connected_frame2d.v1` extends the bounded corotational frame
pipeline from the rectangular portal to a connected planar graph. It remains an
experimental, non-promoted candidate.

The v1 compiler accepts 2–128 unique XY nodes and 1–256 two-node members. The
graph must be connected and may branch, but parallel members between the same
node pair are rejected. Each support row may constrain a non-empty unique subset
of `UX`, `UY`, and `RZ`; one or more support nodes are required.

Support rows may include `prescribed_values` for constrained components. Those
terminal values are scaled by every load factor, included in the problem hash,
checked byte-for-byte in committed checkpoints, and replayed through dense or
native sparse assembly. A fully constrained prescribed-only model uses the
reaction-only no-solve disposition: it commits exact checkpoints and reactions
without executing Newton or making a convergence claim.

For a ready result, the compiler and adapter bind connected topology, support and
equation scaling, proportional nodal loads and prescribed values, checkpoint
ancestry, solver/assembly identity, no-fallback execution, the full-load terminal
contract, exact engineering recovery, and canonical checkpoint-chain replay.

```bash
python -m structural_analysis.api.nonlinear_frame_cli \
  examples/public_corotational_branching_frame.json \
  --profile corotational_connected_frame2d.v1 \
  --load-steps 4 \
  --matrix-backend scipy_sparse_spsolve_cpu \
  --out connected-result.json \
  --report-out connected-report.json \
  --checkpoint-out connected-checkpoint-chain.json
```

The same `analyze_nonlinear_frame` Python entry point exposes bounded dense direct
displacement control for one free `UX` or `UY` coordinate. It uses augmented
consistent Newton, proportional support-motion coupling, exact rollback,
terminal-parent engineering recovery, a complete epoch-zero checkpoint chain,
and byte-exact accepted-checkpoint restart. The lower-level solver remains
available as an internal assembly contract and is documented separately.

Finite rigid offsets, optional RZ end releases, uniform dead loads in explicitly
declared chord-bound member-local axes, and self-weight from explicit SI
mass-per-length/global-gravity inputs are executed within the bounded connected
profile. Density-derived self-weight, arbitrarily rotated local axes,
unified-profile arc-length control, direct-control CLI flags and native sparse
augmented execution, disconnected graphs, parallel members, production-scale
conditioning, independent Level 2 comparison evidence, design authority, and
release promotion remain outside this slice.
