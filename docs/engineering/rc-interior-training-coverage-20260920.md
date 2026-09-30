# Two additional interior training groups with preserved original labels

The prior [99-label runtime campaign](rc-expanded-runtime-campaign-20260920.md)
admitted proposals only in the middle B geometry group. The extreme A/C groups
lay outside complementary training coverage. This experiment adds two declared
interior synthetic groups before observing their labels, without rerunning the
old 99 samples or executing reserved validation/holdout cases.

| New group | L-frame member lengths | Twelve target ratios in mm, before amplitude scaling |
| --- | --- | --- |
| D | 2.7 m, 2.2 m | -0.5, -1.5, -3, -6.2, -3, 1, 4, 5.2, 2, -2, -4.2, 0 |
| E | 3.3 m, 2.6 m | -0.5, -1.5, -3, -7.2, -3, 1, 4, 5.8, 2, -2, -5.2, 0 |

Each group uses amplitudes 0.5, 1.0 and 1.5. The original material, cross section,
constant 20 kN load, solver tolerances, extended line-search factors and retained
twofold arithmetic remain unchanged. Whole-group split checks run over all
seventeen declarations: fifteen training cases and two reserved cases. They
produce five separate groups of three amplitudes; this is a conservative split
check, not authentication of five independent projects or structural families.

## Actual generation and source-bound audit

All six new reference/secant/fresh-reference generation comparisons complete
with eligible labels, yielding **66 new samples**. They cost **234 core calls and
1,212 Newton iterations/linear solves**, with no unknown generation work. The
learning-study interval is 86.013788545 seconds; the enclosing process is
88.147518242 seconds. One 66-sample SVD ridge fit completes as part of the existing
generation API (0.023613455 seconds). It is retained, not promoted or evaluated.
The old label cost remains separate; the 66 new samples are not cost-free data.

The auditor checks all 66 original step byte hashes, accepted coordinates,
parent identities and context files. It recomputes features and secant correction
bindings against the declared models/requests for both old and new data, validates
policy/sample identities, and requires identical feature/solver metadata before
considering the combined **165 samples**. It performs no fits or solver calls.
Both reserved cases have explicit `not_attempted` evaluation rows and zero
evaluation core calls.

## Reference-parent range coverage, not measured proposal benefit

For each whole group, all its three amplitudes are excluded. Bounds are computed
from the other **132 samples**, with the existing 0.1 OOD margin and unchanged
floor. These are full original reference-parent feature checks, not tests of
actual proposals on a divergent learned path.

| Excluded group | Eligible original parent samples |
| --- | ---: |
| A | 0 / 33 |
| B | 33 / 33 |
| C | 0 / 33 |
| D | 33 / 33 |
| E | 33 / 33 |

Coverage now includes 99 parents across B/D/E, versus 33 in B in the earlier
three-group data. Extremes remain outside the complementary range. No gate was
loosened, no old failure was removed, and no new policy has demonstrated lower
runtime. The next comparison must refit from complementary groups, preserve
whole paths and all costs, and continue to select secant unless actual benefit
is demonstrated. Reserved evaluation paths remain untouched by this experiment.

## Reproduction and preserved evidence

Generation driver: `scripts/run_rc_interior_training_coverage.py`, numeric source
`15db4fae0aa65b76ea6d11a5fc4f540fbc2bee58`. It verifies the original label packet's
pinned inventory and exact declarations before generating only D/E. Of its 468
archived files, the pre-existing changes from the old label snapshot are confined
to corrected diagnostic feature names and their history-coverage caller; the
numerical solver/feature-generation sources are unchanged. All archived bytes
were compared against Git before execution.

Auditor: `scripts/audit_rc_interior_training_coverage.py`, audited/tested revision
`97dc95d97077bcd6763f75e409741b6c53033542`. Focused checks reject duplicate JSON
keys and changed declared requests and preserve immutable prior probe records:
**3 tests pass in 1.97 seconds**. Ruff and whitespace checks pass. These synthetic
checks are separate from the actual 66-step source audit.

Packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-interior-training-uxct1ncc`.
The 1,955 payload files total 97,392,185 bytes, excluding Python cache files.
All recorded lengths and hashes were checked. Inventory SHA-256:
`23d28a47d891e1b45d7306007529a78d203a436677af0fd5fe9e7dbe4061af92`.
The full audit retains all 165 parent range decisions and violated feature names;
the companion summary keeps counts, work and source identities. The original
99-label packet and its failed post-generation diagnostic exit remain unchanged.
