# G1 Physical-Consistent Global Newton Operator (opt-in, non-promoting)

Step E of the D→E→F plan. Adds an **opt-in** physical-consistent global Newton
operator next to the existing default corrector, plus a JVP parity probe. This
PR adds an opt-in physical-consistent global Newton operator probe. It does not
change the default solver path, does not promote G1, and does not regenerate
tracked evidence.

- Operator helper: `implementation/phase1/g1_global_newton_operator.py`
- Probe driver: `implementation/phase1/run_g1_physical_consistent_operator_probe.py`
- Tests: `tests/test_g1_physical_consistent_operator.py` (hermetic, synthetic)
- Output: `release_evidence/productization/g1_physical_consistent_operator_probe.local.json`
  (untracked `*.local.json`; never promoted, never committed)

## Operator modes

| enum | value | role |
| --- | --- | --- |
| `GLOBAL_NEWTON_OPERATOR_CURRENT` | `current_normalized_frame_geometric` | **default**; D-named stall driver; kept as regression baseline |
| `GLOBAL_NEWTON_OPERATOR_PHYSICAL` | `physical_consistent_frame_shell_material_geometric` | opt-in; matrix-free `dR/du` of the physical residual |

`DEFAULT_GLOBAL_NEWTON_OPERATOR` is always `current_normalized_frame_geometric`.

## What the physical operator is

A matrix-free directional derivative of the physical residual
`R(u, lambda) = F_int(u) - lambda * F_ext`:

```
J_phys(u) . v = (R(u + eps v) - R(u - eps v)) / (2 eps)
```

Because it is taken directly from the physical residual it uses **no** solver-only
lambda damping and **no** service-material reduction.

## Mandatory E success criteria (all locked by tests)

1. default operator stays `current_normalized_frame_geometric`;
2. the physical operator excludes the solver-only lambda damping
   (`uses_solver_normalization_lambda=false`, `normalization_lambda_excluded=true`);
3. the probe report is non-promoting (`is_probe_only=true`,
   `promotes_g1_closure=false`, no G1 closure field even when parity passes);
4. the matrix-free JVP matches the physical residual (analytic Jacobian action and
   independent finite difference) within tolerance.

## Provenance note

The 0.656 continuation checkpoint consumed by the D audit is an ephemeral artifact
no longer on disk, so this probe runs on a deterministic seeded *representative*
physical residual (SPD stiffness + smooth geometric nonlinearity). Provenance is
recorded as `representative_bounded_physical_system`. Breaking load_scale 0.656 is
an F-stage signal, not an E criterion.

## Deferred to F

Actual line-search / trust-region residual reduction on a live continuation state
is F-stage work; the probe reports `line_search_preview.status = "deferred_to_F"`.
