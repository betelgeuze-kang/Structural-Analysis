# Phase 2 geometric-nonlinear benchmark seeds

This slice adds three deterministic verification kernels with explicit analytic
truth. It does not introduce or claim a general geometric-nonlinear frame solver.

The pinned-pinned Euler column assembles conventional Euler-Bernoulli elastic and
unit-compression geometric stiffness matrices. Meshes with 2, 4, 8, and 16
elements converge from above to `pi^2 EI / L^2`; the receipt records generalized
eigen-residuals, nodal sine-mode MAC, and observed convergence order.

The modal P-Delta case reuses the same `K`, `Kg`, and first FE eigenvector. For
compression ratios below one, solving `(K - P Kg) u = K phi` must reproduce the
exact first-mode amplification `1 / (1 - P / Pcr)`. This is a column eigenmode
identity, not evidence for a general 2D or 3D P-Delta frame implementation.

The shallow-arch case uses two symmetric finite-rotation truss bars. Its exact
displacement-controlled equilibrium curve crosses the first limit point, the
inverted negative-load branch, and the later rehardening branch. The analytic
consistent tangent is checked against a same-point central difference, and the
internal force is independently checked as the derivative of strain energy.
This traces a snap-through-shaped path by prescribed displacement; it is not an
arc-length solver and is not the Lee frame benchmark.

A separate scalar continuation slice now reuses this exact two-bar equilibrium
in `phase2_shallow_arch_arc_length_result.json`. That receipt solves equilibrium
and the spherical constraint together, crosses the first limit point, and checks
rollback and checkpoint restart. It does not change the claim boundary of this
older displacement-controlled artifact or constitute a general multi-DOF
frame/shell arc-length solver.

`phase2_coupled_shallow_arch_vector_arc_length_result.json` then exercises a
dense vector augmented Newton solve on a conservative coupled two-DOF extension
with an exact scalar reduction. That closes a reusable vector-kernel contract,
but still does not connect a frame/shell element formulation or close the Lee
frame, sparse production, HIP, or G1 gates.

Artifacts:

- `implementation/phase1/release_evidence/productization/phase2_geometric_nonlinear_benchmark_result.json`
- `implementation/phase1/release_evidence/productization/phase2_geometric_nonlinear_benchmark_summary.json`
- `src/structural_analysis/schemas/geometric_nonlinear_benchmark_v1.schema.json`

Run:

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_geometric_nonlinear_benchmarks.py \
  tests/test_build_phase2_geometric_nonlinear_benchmark_artifacts.py
python3 scripts/build_phase2_geometric_nonlinear_benchmark_artifacts.py
python3 scripts/build_phase2_geometric_nonlinear_benchmark_artifacts.py --check
```

The artifact remains `status=partial` even when all implemented rows pass.
General P-Delta frames, the Lee frame, a multi-DOF frame/shell arc-length
continuation algorithm, continuum cantilever large rotation, corotational
frame/shell elements, material-geometric coupling, published or experimental
validation, and sparse ROCm/HIP numerical parity remain explicit blockers.
