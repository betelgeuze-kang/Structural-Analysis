# Corotational Fiber-Frame J1-J5 Adapter

This candidate binds the existing stateful corotational 2D fiber-frame solver to one
explicit compiler profile:
`planar_one_bay_one_story_portal_explicit_fiber_section.v1`.

The profile accepts exactly four nodes, two columns, one top beam, two fully fixed
bases, zero prescribed support movement, and proportional nodal reference loads on
the top nodes. Execution is limited to load-controlled, dense CPU Newton solves. It
is a narrow productization bridge, not a claim of general frame topology.

## Bound stages

| Stage | Bound contract |
| --- | --- |
| J1 | Portal topology, global DOF map, and assembled operator |
| J2 | Translational/rotational equation scaling and scaled residual |
| J3 | Accepted checkpoint ancestry for every load step |
| J4 | Solver iterate, trial assembly, and material-state binding |
| J5 | Full-load convergence and terminal checkpoint identity |

Every receipt and the aggregate adapter use canonical SHA-256 content hashes. Stage
receipts carry their frozen JSON bodies, and the adapter manifest embeds the complete
compiler record, so a standalone consumer can recompute the compiler, stage, and
aggregate hashes. The retained-source validator additionally replays the typed
problem and load path, validates checkpoint ancestry, and fails closed on metadata,
stage, schema, or hash drift.

## Authority boundary

The adapter establishes a bounded **convergence candidate** only. A standalone
manifest proves internal hash consistency, not authenticity of the problem or solver
sources; source authenticity requires the retained typed objects and replay. The
adapter does not create numerical ResultIR authority or reaction, member-force,
section-resultant, or fiber authority. Those axes remain `not_created` on the adapter;
the separate bounded recovery result can establish exact candidate values without
mutating or broadening this source contract. See
[`corotational-fiber-frame-engineering-recovery.md`](corotational-fiber-frame-engineering-recovery.md).

This adapter profile also excludes displacement control, sparse execution, general
topology, member-end releases, rigid offsets, distributed member loads, and direct
public authority. Exact recovery is a companion contract rather than an adapter
stage. The bounded unified API now composes both contracts for a typed Python/CLI
candidate, but independent Level 2 external-solver evidence remains unattached, so
the capability stays experimental and non-public in the canonical registry.

The machine-readable schema is
`src/structural_analysis/schemas/corotational_fiber_frame_j1_j5_adapter_v1.schema.json`;
focused replay and tamper tests are in
`tests/test_corotational_fiber_frame_j1_j5.py`.
