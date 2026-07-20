# Public bounded two-bar nonlinear truss vertical slice

## Purpose

This slice connects a real neutral `CanonicalModel` input to the retained
stateful material-geometric Newton path through a public Python API and a
dedicated CLI. It proves one model-to-solve-to-result path without claiming a
general truss product solver.

## Public API

```python
from structural_analysis.api import (
    PublicTwoBarTrussConfig,
    analyze_public_two_bar_truss,
    validate_public_two_bar_truss_result,
)

result = analyze_public_two_bar_truss(
    model,
    PublicTwoBarTrussConfig(load_steps=10),
)
report = validate_public_two_bar_truss_result(result)
```

## CLI

```bash
python -m structural_analysis.api.nonlinear_truss_cli model.json \
  --load-steps 10 \
  --out result.json \
  --report-out report.json
```

A console-script registration is proposed as
`structural-analysis-nonlinear-truss`. The module invocation remains the
canonical direct path for this bounded draft.

Both output paths are validated before model loading. They must be distinct and
must not alias or nest with the model input.

## Exact accepted model scope

The canonical model must contain:

- units `m` and `kN`;
- global `XYZ`, `Z`-up coordinates;
- exactly three planar nodes;
- two base nodes at equal elevation and equal horizontal distance from the apex;
- exactly two `truss` or `axial` elements, one from each base to the apex;
- identical material and section references for both bars;
- one explicit positive area;
- one explicit bilinear combined-hardening steel material;
- both base nodes restrained in `UX` and `UY`;
- a free apex in `UX` and `UY`;
- exactly one downward apex nodal load with no horizontal, out-of-plane, or
  moment component.

Any deviation is an explicit pre-solve blocker. The adapter does not infer,
repair, coarsen, or silently drop unsupported model semantics.

## Solve and state contract

The adapter maps the accepted canonical geometry and properties to the existing
bounded `StatefulTwoBarTrussProblem` and runs explicit ordered load targets.
Each step:

- evaluates every trial from one immutable accepted material parent;
- uses the full material plus initial-stress geometric tangent;
- requires Newton residual/increment and line-search gates;
- disallows fallback and regularization promotion;
- commits displacement and both material states together;
- or returns the exact accepted state after rollback.

The result exposes canonical model identity, nodal displacement, support
reaction, element axial force/strain, material state hashes, dissipated energy,
convergence history, and the bounded claim boundary.

## Authority boundary

The result is a Developer Preview application envelope, not an Engine v2
`NumericalResultIR` or `EngineeringResultIR`.

It does not grant:

- arbitrary topology or 3D truss support;
- frame, shell, cable, contact, or foundation behavior;
- multiple load cases or prescribed movement;
- arc-length traversal;
- production sparse or ROCm/HIP execution;
- nonlinear numerical/reaction/member-force authority;
- design/code compliance or commercial readiness;
- full-building or G1 closure.

The next stacks are:

1. replace the retained benchmark-owned problem bridge with reusable assembly
   based on the extracted corotational truss kernel;
2. adapt accepted material states into `MaterialStateBundle`;
3. add nonlinear result/recovery authority;
4. expose the same path through the general `AnalysisConfig` dispatcher only
   after those contracts are reviewed.

## Focused validation

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_corotational_truss2d_element.py \
  tests/test_public_two_bar_truss_api.py
python3 -m ruff check \
  src/structural_analysis/elements/corotational_truss2d.py \
  src/structural_analysis/api/nonlinear_truss.py \
  src/structural_analysis/api/nonlinear_truss_cli.py \
  tests/test_public_two_bar_truss_api.py
```
