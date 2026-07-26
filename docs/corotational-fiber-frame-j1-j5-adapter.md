# Corotational Fiber-Frame J1-J5 Adapter

This candidate binds the existing stateful corotational 2D fiber-frame solver to a
single, explicit compiler profile:
`planar_one_bay_one_story_portal_explicit_fiber_section.v1`.

The profile accepts exactly four nodes, two columns, one top beam, two fully fixed
bases, zero prescribed support movement, and nodal reference loads. It is a narrow
productization bridge, not a claim of general frame topology.

## Bound stages

| Stage | Bound contract |
| --- | --- |
| J1 | Portal topology, global DOF map, and assembled operator |
| J2 | Translational/rotational equation scaling and scaled residual |
| J3 | Accepted checkpoint ancestry for every load step |
| J4 | Solver iterate, trial assembly, and material-state binding |
| J5 | Full-load convergence and terminal checkpoint identity |

Every receipt and the aggregate adapter use canonical SHA-256 content hashes. The
validator replays the retained problem and load path, validates checkpoint ancestry,
and fails closed on metadata, stage, schema, or hash drift.

## Authority boundary

The adapter establishes a bounded **convergence candidate** only. It does not create
numerical ResultIR authority or reaction, member-force, section-resultant, or fiber
authority. Those axes remain `not_created` until exact engineering recovery is bound
and independently verified. It also does not promote the capability to the public API.

The machine-readable schema is
`src/structural_analysis/schemas/corotational_fiber_frame_j1_j5_adapter_v1.schema.json`;
focused replay and tamper tests are in
`tests/test_corotational_fiber_frame_j1_j5.py`.
