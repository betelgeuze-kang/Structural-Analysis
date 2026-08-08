# N1 CPU mathematical closure gate

N1 is a separate mathematical gate from the production ROCm/HIP G1 worker.
It combines two exact-replayed evidence lanes:

1. the actual uncoarsened MGT 70,560-equation finite-chord axial equilibrium
   path, including the historical `0.656` reproduction, adaptive continuation,
   direct and stepped full-load `1.0`, residual/increment gates, accepted-state
   tangent refresh, physical-merit line search, zero fallback/regularization,
   and byte-exact checkpoint restart;
2. the bounded four-family stateful material Newton path, including consistent
   directional tangents, trial/commit/rollback, residual/increment gates,
   physical merit, zero fallback/regularization, and byte-exact restart.

Run the aggregate verifier from the N1 worktree:

```bash
PYTHONPATH=$PWD/scripts:$PWD/src:$PWD/implementation/phase1 python3 \
  scripts/build_n1_cpu_mathematical_closure_gate.py \
  --check --require-commit-bound

python3 -m pytest -q \
  tests/test_build_n1_cpu_mathematical_closure_gate.py
```

The gate is `ready` only when all sixteen named evaluations pass. Its claim is
deliberately narrower than product G1: the four stateful laws are not presented
as connected to the actual-MGT full frame/shell operator, reference-geometry
bending/torsion is not promoted, and no ROCm/HIP claim is made. The generator,
schema, receipt, test, and this runbook must be committed and reviewed in the
separate N1 PR before branch promotion.

The generator and schema are committed before the final receipt is produced.
Generate that receipt with the contract commit as its source:

```bash
PYTHONPATH=$PWD/scripts:$PWD/src:$PWD/implementation/phase1 python3 \
  scripts/build_n1_cpu_mathematical_closure_gate.py \
  --source-commit "$(git rev-parse HEAD)" --require-commit-bound
```

The receipt may then be committed in a later evidence-only descendant. Validation
requires the recorded source commit to remain an ancestor and every declared
generator/schema/upstream input to remain byte-identical to the recorded Git
objects. This avoids a cyclic receipt whose exact replay changes merely because
the receipt itself was committed.
