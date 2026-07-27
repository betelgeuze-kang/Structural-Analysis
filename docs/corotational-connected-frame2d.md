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

The lower-level assembly package also exposes a bounded dense direct
displacement-control candidate with augmented consistent Newton, proportional
support-motion coupling, exact rollback, and accepted-checkpoint restart. That
internal solver is documented separately and is not wired into this unified
J1–J5 profile.

Finite rigid offsets, optional RZ end releases, and uniform dead loads in the
initial member-local axes are executed within the bounded connected profile.
Automatic self-weight, user-rotated local axes, unified-profile direct
displacement and arc-length control, disconnected graphs, parallel members,
production-scale conditioning, independent Level 2 comparison evidence, design
authority, and release promotion remain outside this slice.
