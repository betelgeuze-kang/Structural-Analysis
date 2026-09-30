# Package preparation, exact similarity and protected CI boundary

At source `7b06d0005ed460ff01e09c222e093d624128ac7d`, five previously absent
external-comparison input packages were generated successfully: linear (2 cases),
negative (3), scaling (2), modal/buckling (3), nonlinear material recovery (6).
The 16 cases comprise 66 files. Package manifests explicitly deny external
execution, independent validation and promotion credit.

The ten-module package/ingestion/promotion run finished with **76 passed and
8 failed in 316.25 seconds**. Seven promotion tests could not construct their
fixtures because external code-to-code records lacked current execution binding
or had stale sources. Those tests did not reach their intended promotion checks
and remain unresolved. Synthetic imported-result fixtures are not independent
external executions.

The other failure required a strictly positive normalized difference in the
characteristic-length similarity case. Current calculations produced exactly
zero difference. The two inputs are distinct (for example node N2 is at 4 m
versus 16 m); their normalized outputs agree. The test now allows zero while
retaining its upper bounds, solver tolerances and loose-tolerance rejection test.
All **9 scaling-package tests passed** after that change; the complete 84-test
run was not repeated.

## Protected evidence correction

Native PR Fast run `34733276456`, scope job `103660431388`, rejected the six
recently refreshed protected productization records. Its classification policy
is unchanged. Those six files are restored byte-for-byte to PR base
`4de4e3f55aae1d267cf704cec7d7533f3a627498`, after preserving the fresh local
records and their hashes. Consequently, the previously reported current-source
checks for those regenerated files describe the retained local runs, not the
protected files now checked into this development branch.

The full Python CI's ephemeral materialization step now also executes the five
bounded material/continuation builders before external preparation. Its existing
reaction-only regeneration remains. External receipt and licensing failures still
fail the stage, and full test shards still require successful preparation. No gate,
permission or external receipt was bypassed. All **16 repository Python workflow
contract tests passed**. Bare local full pytest still requires the documented
preparation; no clean-checkout full-suite pass is claimed.

Raw logs, package inventory, manifests, JUnit outputs and preserved records:
`/tmp/structural-case-package-preparation-hzsizzdq`. The preserved protected files
and restored byte hashes are indexed in `protected-refresh-backup/inventory.json`.
Hosted native completion and the seven promotion-fixture failures remain open.
