# RC direct-control initial guesses

`solver_config.initial_guess` accepts `parent` (the default) or `control_target`.
The default keeps the existing configuration manifest, request normalization,
and restart identity. An explicit `parent` normalizes to the omitted field.

`control_target` starts each trial with the controlled translational coordinate
set to the authored target. Other free coordinates and the load factor retain
their parent values. This adds no solve, retry, target subdivision, or material
commit. The unchanged Newton, line search, equilibrium/control checks and
rollback rules determine acceptance. Its manifest uses
`small-displacement-rc-fiber-direct-control.v2` and includes the selected guess;
restarts from the other mode are rejected before prefix replay.

## Why this is an explicit choice

A synthetic fixed-guided axial example reaches a concrete damage kink at
0.3 mm. Starting the next 1.5 mm target at parent equilibrium makes its small
control residual compete with large force residuals from the changed tangent;
all six line-search trials fail. The control-feasible guess completes the same
nine authored targets, including steel yielding and tensile/compressive damage.
Serialized restart matches continuous execution exactly, and a failed post-yield
trial preserves the parent state.

This choice is not universally better. Applying it as a new default caused an
existing multi-DOF RC unloading example to fail. Keep the parent mode for existing
requests; select and validate the alternative for a declared model and path.
There is no automatic fallback between the modes or speedup claim.

The request decoder, durable worker and frontend artifact reviewer carry and
validate this choice. The frontend lifecycle fixture covers worker termination,
restoration and quantity-report review for the option with synthetic input.
The nonlinear fixed-guided regression constructs an internal problem; it does
not add that boundary to the public model compiler. Neither test establishes
TC11 material/initial-state correspondence, geometric nonlinearity, physical
validation, design approval or release readiness.
