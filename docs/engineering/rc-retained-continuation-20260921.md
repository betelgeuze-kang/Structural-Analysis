# Retained-coordinate frozen-parent continuation

The experimental frozen-parent continuation can now run with the existing
`retained-twofold-refinement.v1` arithmetic profile. Ordinary binary64 behavior
and all comparison/acceptance tolerances remain unchanged. This is opt-in
benchmark support, not a production default or a learned policy.

The native initial-seed interface consumes absolute high coordinates. Retained
solver coordinates are instead increments from the unchanged material parent.
The first trial now converts its initial solver coordinates to absolute values;
subsequent trials carry `absolute_augmented_coordinates_m`, including the load
factor. The original parent retains its coordinate compensation and material
state. No intermediate accepted material checkpoint becomes the next parent.
The proposal report names the seed representation `binary64_absolute_high`.

The artifact replayer accepts either the original binary64 report or the complete
existing retained profile. It passes the arithmetic configuration through to the
fresh execution and rejects partial/mixed profiles. Trust-region proposals still
require binary64 coordinates.

## Focused numerical regressions

Two actual L-frame cases use N3 UY control, constant N3 FY = -25 kN, and targets
`(-A/2, -A, A/2)`: short geometry (2 m, 1.5 m), A = 2 mm; long geometry (3 m,
2.5 m), A = 40 mm. Both explicitly enable terminal polishing as required by the
retained profile. This changes an algorithm option as well as arithmetic relative
to the earlier default binary64 study; it does not isolate either effect alone.

Both proposal paths complete, preserve their parent at every internal stage, and
pass the unchanged complete-history comparison against a fresh reference. Each
uses sixteen internal native trials. The test verifies absolute seed handoff,
retained compensation, full artifact reproduction and fresh-reference gates.
The earlier binary64 failures remain in the original breadth-study evidence.

These are focused tests, not a frozen-source balanced performance campaign. Test
source revision strings are synthetic labels. Timing is not interpreted as speed
improvement. Neither external physical accuracy, independent project coverage,
learned benefit nor product/design approval follows from these tests.

## Local validation receipt

The four focused suites initially reported 97 passes and three expected-message
mismatches in 101.74 s. After updating those expectations, the three affected
cases and both retained regressions passed (five tests, 53.34 s). Two additional
preflight tests reject partial and mixed retained profiles before output creation
(1.60 s). Thus all 102 distinct focused cases passed across these runs; this was
not a single clean full-repository run. Ruff and `git diff --check` pass.

| Case | Proposal maximum absolute difference, mixed SI | Replayed JSON files | Fresh replay native calls | Fresh replay Newton iterations |
| --- | ---: | ---: | ---: | ---: |
| Short / 2 mm | 0 | 123 | 32 | 191 |
| Long / 40 mm | 5.820766091346741e-11 | 126 | 33 | 228 |

Both fresh replays match all numerical artifacts and pass all reference comparisons.
Replay costs above include its four arms and internal continuation trials; they
are additional to the original test execution. No timing ratio is claimed.

Preserved test packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-retained-continuation-tests-ne4jlr3q`.
All 511 inventory entries were reread and hash/length checked. Inventory SHA-256:
`9fa2e2ee0cd8bdd6d1d398389b7031fce1424d4c8235e6103888a523ada723e0`.
The packet includes original/replayed files, changed implementation/test bytes,
and the initial failed and corrected test logs. It does not archive the complete
repository or authenticate synthetic source labels as commit identities.
