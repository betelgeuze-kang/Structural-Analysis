# Connected Corotational Frame2D Profile

`corotational_connected_frame2d.v1` lifts the bounded corotational solver from one
rectangular portal to a connected planar member graph. The compiler accepts 2-128
unique XY nodes and 1-256 unique two-node RC fiber members, rejects disconnected and
duplicate-edge graphs, records node degree and branching nodes, and binds every member
contract into J1.

Supports may be distributed across any number of nodes and may restrain any non-empty
unique subset of `UX`, `UY`, and `RZ`. Optional `prescribed_values` keys must be a subset
of those restrained DOFs. Translation values use metres and `RZ` uses radians. The v1
history is proportional:

`u_prescribed(lambda) = lambda * u_prescribed(full load)`

The assembly inserts this value before every element integration. Checkpoints require
the exact constrained value for their stored load factor; terminal-parent engineering
replay independently rebuilds it. Constrained residuals produce reactions, including in
a prescribed-only fully constrained model where Newton is explicitly not executed.
Public compilation chooses a power-of-two rotational coordinate scale so physical and
generalized checkpoint coordinates round-trip bit-exactly.

The profile supports proportional nodal `FX`, `FY`, and `MZ`, bounded RZ end releases,
finite-rotation global-XY rigid offsets, uniform initial-local-axis dead loads, and the
same dense or native sparse load-control backends as the portal. Member feature
contracts and local release-equilibrium response hashes are included in J1-J5. Parallel
members, disconnected graphs, time-varying prescribed histories, broader release/load
families, external Level 2 validation, and design/release authority are not included.
See `docs/corotational-member-features.md` for the exact input and operator boundary.
