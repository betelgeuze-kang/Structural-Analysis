# Explicit linear physical displacement control

The experimental planar corotational RC route can control an explicitly authored observation `g(u) = sum(c_j * u_j)` in meters. Select `linear-physical-displacement-observation.v1` with 1 to 48 distinct node/component terms. UX and UY coefficients are dimensionless; RZ coefficients have units m/rad and are explicit signed lever arms. The solver does not infer a test measurement formula, support correction, lever arm, material value, initial state, or target reduction.

The old single free UX/UY route retains its profile, formulas, output fields and numerical pathway when no observation is selected. The selected native route records `dense-augmented-linear-physical-displacement-control.v1`, a separate augmented formula hash and the exact normalized operator identity. Ordinary package source changes still change the source fingerprint; old source-bound receipts do not qualify the new implementation.

For the public API, omit `control_node_id` and `control_component`, and supply:

```python
control_observation = {
    "schema_version": "linear-physical-displacement-observation.v1",
    "terms": [
        {"node_id": "tip", "component": "UY", "coefficient": 1.0},
        {"node_id": "support", "component": "UY", "coefficient": -1.0},
        {"node_id": "support", "component": "RZ", "coefficient": -1.0},
    ],
}
```

This illustrates a one-meter signed rotation correction; it is an authored software input, not an experimental specimen definition. Native callers use `LinearPhysicalDisplacementObservation(((tip_dof, 1.0), (support_dof, -1.0), (support_rz_dof, -1.0)))`. Native terms are sorted by global DOF for deterministic identity. Duplicate terms, zero or nonfinite coefficients, boolean and unsafe integer coefficients, invalid components/indices, and operators without a nonzero finite free gradient are rejected. Simultaneously selecting the old node/DOF control and an observation is rejected.

With physical coordinates `u = S q`, the free gradient is `c_f S_f`. The rotation entries of `S` are `1 / rotation_coordinate_scale_m`; using raw RZ generalized coordinates would change the physical observation. Prescribed displacements remain proportional to the solved load factor: `u_p = lambda * ubar_p`. They contribute to both the control residual and its last Jacobian entry. With augmented coordinate `eta = beta * lambda`, that entry is `w * sum(c_p * ubar_p) / beta`. The selected equilibrium load-factor column comes from the admitted native frame assembly, including consistent member-feature condensation and prescribed-support coupling. The canonical public compiler still admits its existing nodal-load scope; this feature adds no public distributed-load model profile. The observation is linear even when the frame equilibrium and material law are nonlinear.

Both direct paths and bounded subdivision evaluate the accepted physical observation before each increment. Reversal, subdivision, trial state, accepted material/frame commit and exact failed-step rollback use the existing transactional route. The observation is bound into the continuation context together with authored targets, problem, solver policy, source fingerprint, depth and total attempt cap. Changing a term on resume is rejected. Public restart also verifies the entire accepted prefix by fresh replay before advancing. A raw frame checkpoint is a material/frame state codec; it does not independently attest a measurement operator. The source-bound control continuation supplies that binding.

Durable v6 and isolated v7 requests explicitly select this mode by replacing `config.control_node_id` and `config.control_component` with `config.control_observation`; the other config and execution fields remain required. Canonical request bytes and request/resume hashes bind the selected operator. Native continuation validation, recorded invocation outcomes, worker receipts, accepted response history and saved reports preserve that binding. Saved reports declare both the original named-node observation and its normalized global operator. Their `control_displacement_m` is computed from the complete saved physical node vector, including support and RZ terms. Saved-report export and Workbench review perform no numerical replay or current-source fingerprint calculation.

Targets remain bounded to 255, without adjacent repeats. Total control attempt, subdivision depth, API invocation and report byte limits are unchanged. This feature does not turn a 30,574-record history into one admitted job, introduce a time-varying axial-load schedule, remove repeated holds, or silently downsample experimental data. Those are separate driver contracts.

A linear support/rotation correction cancels infinitesimal rigid translation and rotation for appropriate explicitly chosen coefficients. It generally does not cancel finite rigid rotations: a one-meter correction can retain `theta - sin(theta)`. This is not a finite-rotation drift operator. CC-3.3-10 source correspondence, material laws, initial state and fixed member comparison remain held until their independent source and applicability requirements are satisfied. Software workflow tests do not establish specimen reproduction, independent physical validation, design approval or release readiness.
