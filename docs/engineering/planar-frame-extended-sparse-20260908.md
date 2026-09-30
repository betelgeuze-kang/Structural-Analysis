# Explicit extended sparse planar-frame path

The connected planar Developer Preview can explicitly select
`scipy_sparse_splu_cpu_exact_1536` for native CSR Newton assembly and SuperLU
increments under the existing strict public diagnostic thresholds. It retains
the existing constitutive laws, convergence tolerances, accepted-state replay,
engineering recovery and restart contracts. This expands an algebraic diagnostic
scope; it does not supply independent numerical validation or release approval.

The later accepted-state implementation at `e30598048` also retains the extended
path's accepted tangents and engineering recovery in CSR, and connects the
backend to durable v1 requests and read-only Workbench review. See
[the accepted-state and resource observation](planar-frame-sparse-state-runtime-20260908.md)
for exact compatibility, reduced stored-array bytes and increased validation time.
The numerical observations below retain their original source and scope.

## Use and unchanged bounds

```python
from structural_analysis.api.planar_frame import PlanarFrameConfig, analyze_planar_frame
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND,
)

result = analyze_planar_frame(
    document,
    PlanarFrameConfig(
        load_steps=2,
        matrix_backend=VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND,
    ),
)
```

The same choice is available through the existing planar CLI:

```bash
PYTHONPATH=src python3 -m structural_analysis.api.planar_frame_cli \
  examples/planar_frame_rc_portal.json \
  --load-steps 2 --matrix-backend scipy_sparse_splu_cpu_exact_1536 \
  --out /tmp/extended-planar-result.json \
  --report-out /tmp/extended-planar-validation.json \
  --checkpoint-out /tmp/extended-planar-checkpoint.json
```

Use new output paths. The CLI retains its existing path-alias, atomic-output and
restart handling. The unified nonlinear-frame CLI also exposes this explicit
corotational choice; the fixed-chord profile continues to reject sparse backends.

| Backend | Exact condition diagnostic equation limit | Default |
| --- | --- | --- |
| `numpy_linalg_solve_dense` | Separate dense solver scope | Yes |
| `scipy_sparse_spsolve_cpu` | 256 | Existing sparse opt-in |
| `scipy_sparse_splu_cpu_exact_1536` | 1,536 | New explicit opt-in |

Both sparse choices use maximum matrix 1-norm condition number `1e12`, minimum
normalized absolute pivot `1e-14`, and maximum backward error `1e-12`. Neither
regularizes nor falls back to dense on a diagnostic failure. The policy manifest
and hash bind the selected equation limit. Existing 256-equation policy defaults,
factorization calls and diagnostic serialization remain unchanged.

The connected public topology still permits 2–128 nodes and 1–256 members under
its existing semantic restrictions. The 1,536 value is a low-level algebraic
diagnostic limit, not a newly supported public node/model size. The existing
88-node, 87-member, 258-free-equation portal is within that topology but exceeds
the older 256-equation diagnostic bound.

## Verification and resource boundaries

The existing exact condition calculation solves every identity column and takes
the maximum absolute inverse-column sum. It already retains one column at a time;
the old 256 limit was a declared work/verification bound, not storage of a complete
dense inverse. The new option uses the same algorithm and diagnostic schema.
It does not substitute a lower-bound condition estimator or the experimental 3D
backend's looser `1e14` condition / `1e-16` pivot defaults.

All sparse routes use the same native-assembly, diagnostic and acceptance gates.
Public typed and detached ready results check declared storage/backend, diagnostic
counts against both hashes and Newton history rows, the actual vector dimension,
the exact selected policy hash, and observed condition/pivot/backward-error
summaries. Renaming a sparse result to dense cannot bypass those
consistency checks. These metadata checks do not replace source replay or prove
authenticity of arbitrary external JSON. The existing numerical and engineering
source contracts remain required.

A reaction-only path has no free equations and performs no Newton factorization.
It keeps zero diagnostic count, unavailable policy/quality values, and false
sparse-execution flags, with no iterative history or physical scaling/residual
trace bindings; it receives no fictitious sparse-solve credit.

Exact inverse-column diagnostics require one solve per free equation. At the
original implementation recorded below, final committed-state assembly and other
source/recovery paths still allocated dense matrices. The later CSR accepted-state
implementation is recorded separately above. Neither observation establishes
general end-to-end memory scaling or speedup. Independent OpenSees/second-solver,
larger-scale numerical acceptance,
hardware qualification and hosted integration remain separate requirements.

## Numerical issue exposed by the larger model

The first extended 258-equation run passed all sparse diagnostics (condition
number about `5.21e6`, normalized pivot about `0.0041`, backward error about
`1.26e-16`) but failed Newton line search at load factor 0.5. It retained no
engineering or checkpoint authority. A separate unchanged-model diagnostic run
for each backend then reproduced the same failure in dense and extended sparse:
relative residuals `1.2052e-9` and `1.0802e-9`, against `1e-10`, while proposed
increment infinity norms were about `1.09e-16` and `6.43e-17` m against `1e-12`.
Those diagnostic runs are additional attempts, not performance measurements.
Their inputs, failed public results and captured convergence traces are preserved
under `/tmp/structural-extended-sparse-diagnostics/`; the original extended
attempt is under `/tmp/structural-extended-sparse-0gql5z2c/`.

A 90-digit Decimal probe independently reproduced lost small deformations in
the shared corotational kinematics: a unit horizontal chord with `1e-17 m` axial
motion returned zero extension; a `(1, 1)` chord with `1e-17 m` vertical relative
motion returned zero extension and angle despite nonzero high-precision values.
The probe log is `/tmp/structural-stable-kinematics-before.log`.

For relative chord translation no greater than `eps**(1/4) * L0`
(`1.220703125e-4 * L0` in float64), the shared element now evaluates extension
through scaled `(L**2 - L0**2) / (L + L0)` terms, retaining the separate relative
translation. It computes relative rotation from chord cross/dot products.
This is the small-motion regime where direct length subtraction can lose at
least about 13 significand bits. Outside it, the original norm and absolute-angle
evaluation remains, preserving finite rigid-rotation rounding and the signed
principal half-turn branch. There is no strain/force clamp, material-law change,
altered analytic gradient/Hessian, or relaxed physical convergence tolerance.

Twenty-nine new tests compare with independent 90-digit absolute length/angle
references, tiny positive/negative motion, zero displacement, half-turn branches,
large finite chords and both sides of the evaluation switch. Switch errors stay
within the declared float64 rounding bounds; this is not a new material or
physical acceptance threshold. Together with the unchanged basic, elastic,
member-feature and stateful-fiber regressions, 71 tests passed in 5.12 seconds.
The first always-rationalized prototype failed three existing rigid-motion/Lee
parity tests; the final adaptive evaluation passed them without editing their
criteria. Log: `/tmp/structural-stable-kinematics-tests.log`.

The formula change can alter corotational response and checkpoint bits. Existing
artifacts retain their original source provenance and are not rewritten. Restart
still reruns each accepted prefix with the current source and requires exact
canonical checkpoint bytes; a changed replay is rejected. Unchanged legacy
backend policy/serialization does not imply unchanged physical result bytes.

## Actual 258-equation integration

The final numerical implementation ran the original 88-node/87-member model at
load factors 0.5 and 1.0, residual tolerance `1e-10`, increment tolerance `1e-12 m`
and maximum 40 iterations. The input is byte-identical to the failed initial
probe: SHA-256
`d6b1b6d449cbaa6c70f20ab263b672dd15e3f1a2db0e86543554a8f0732d0164`.
Both dense and extended sparse executions converged. All node displacements,
support reactions, member end forces, section and fiber rows passed the existing
`rtol=1e-9, atol=1e-9` comparison. This is same-implementation backend parity,
not independent physical verification.

At the two accepted targets, extended sparse relative residuals were
`5.462510443976498e-12` and `5.506581857162018e-12`, with full increment norms
about `3.82e-16 m`. Dense residuals were `5.458367091648597e-12` and
`5.3803184130174485e-12`. Both backends accepted at iteration 2 for each step,
under the unchanged `1e-10` / `1e-12 m` gates.

| Extended sparse diagnostic | Observed | Required |
| --- | ---: | ---: |
| Factorizations / Newton history rows | 6 / 6 | All diagnostics present |
| Maximum matrix 1-norm condition number | 5,211,958.095674742 | At most `1e12` |
| Minimum normalized absolute pivot | 0.004105729527813366 | At least `1e-14` |
| Maximum backward error | `1.1350631036437995e-16` | At most `1e-12` |
| Fallback / regularization count | 0 / 0 | 0 / 0 |

Every observed increment received a native CSR `(258, 258)` tangent. The bound
policy hash is
`sha256:dd4755cbb4469dff802b102b506b2a67f07272104931eb96b37b0fefa4d326b1`.
Prefix restart replayed the first accepted step and solved the second. Its full
checkpoint bytes, contract bindings, engineering result and all SI rows exactly
matched uninterrupted extended execution. The legacy backend still rejected
258 equations before SuperLU or dense fallback. Reaction-only execution retained
its separate no-Newton contract. External V&V remains unattached, engineering
design remains non-authoritative, and the public result is not release eligible.

The 25-test integration passed in 113.77 seconds. It made five top-level analysis
requests: extended, dense, prefix restart, legacy-cap rejection and prescribed
reaction-only. Internal source/authority replays are included in those calls but
not separately counted. These are correctness checks; their elapsed times are
not isolated backend performance measurements. Earlier failed probes and the
separate neighboring regression runs are outside this five-request group.
Artifacts, original input, source hashes, comparison scope and raw file inventory
are preserved in `/tmp/structural-extended-sparse-pngr8zgq/`; log:
`/tmp/structural-extended-sparse-stabilized-integration.log`.

| Preserved artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Extended public result | 827,233 | `b82a86dbbea9f0dcf0a644b2e6715217d45018cde7c4a7c200af0a36c0b1973c` |
| Extended/resumed checkpoint | 1,434,697 | `aad653633aaa3ce3c129fa61ef4fb59514c54578e9e7b2da0372787f960ebfcf` |
| One-step prefix checkpoint | 943,144 | `aa9286d71d9ece5424fd902c1b56f37bce5b2a751016af1918fad26b7f108c46` |

Separate low-level Newton/diagnostic/configuration regressions passed 59 tests,
including synthetic 257- and 1,536-equation diagonal solves and pre-factorization
rejection at 1,537. These algebraic fixtures do not establish a 1,536-equation
public structural-model validation. The unchanged public/unified/stateful
neighboring regression passed 58 tests in 62.59 seconds, and the CI ownership/
test-target contracts passed 34 in 0.43 seconds. The three new test modules are
registered in the core PR test lane. These groups can overlap and are not summed
as a repository-wide test result.

Final metadata review found two additional contradictions: reducing the diagnostic
count and hash list together while retaining more Newton rows, and relabeling an
iterative result as reaction-only while retaining bound scaling/trace evidence.
Both are rejected. Five focused tests passed in 35.25 seconds after this change,
making one additional extended request and one prescribed-only request; their six
model/result/checkpoint files were byte-identical to the previous successful
artifacts. A final legacy dense/sparse public parity test passed in 4.54 seconds.
Logs: `/tmp/structural-extended-sparse-final-gates.log` and
`/tmp/structural-extended-sparse-final-legacy-gate.log`. Ruff, formatting and
`git diff --check` passed for the final implementation.

## Fixed-source CLI restart

Implementation source was committed as
`e2f6967ec84893aa83f3e56616ede3ff7f9b4f10`. With all other agent edits/tests
finished, one additional planar CLI request used the preserved 258-equation
`model.json` and `prefix-checkpoint.json`, `--load-steps 2` and
`--matrix-backend scipy_sparse_splu_cpu_exact_1536`. Defaults retained the same
iteration and convergence criteria. The driver checked the exact commit and
clean working tree before and after, and rehashed all protected input/reference
files and relevant sources without changes.

The CLI exited 0 with converged artifact/execution/numerical/engineering contracts.
It replayed one prefix step and solved one new step. Its complete result JSON
object equals the same-source API resumed result, with result identity
`sha256:c828708778508142d9942ddfa321b90f3a1f8a799e5e608dce529f0c2444b684`.
Serialization key order differs from the test writer, so raw result-file hashes
are recorded separately. The checkpoint bytes and all engineering/SI responses
exactly match uninterrupted extended execution.

The driver, invocation, untouched-input/source hashes, result, validation,
checkpoint and verification receipt are in
`/tmp/structural-extended-sparse-cli.bUuJXN/`. The 827,300-byte CLI result SHA-256
is `4a05e9e27af7bcaad262396f0c0932dfacb734b6ba6a9f769529083c5c7e3150`;
the 915-byte validation file SHA-256 is
`87aad2a219d1394e4ddfc5d9bbfe100c13cb2b16699570e7f45b707927d4f841`.
The checkpoint has the same 1,434,697-byte hash recorded above. This one extra
request includes its internal source/authority replays without separately
counting them. It is CLI correctness evidence, not a speed benchmark, independent
external verification or release approval. Exact-head hosted checks remain open.
