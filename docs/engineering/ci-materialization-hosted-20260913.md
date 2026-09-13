# Hosted verification of materialization failure retention

At source `f8f2f30fab7e6a56b2ff632c7461691c20d89c37`, basic
[CI run 34749337809](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34749337809)
failed in materialization as before. Both added diagnostic steps succeeded.
Artifact 10315417314 was downloaded through the GitHub API and inspected.

Its ZIP contains exactly the four allowed files, without duplicate members:
context, external code-to-code receipt, modal/buckling receipt and internal
license due-diligence manifest. Context matches the run, source commit and
`verify` job, and retains diagnostic-only/non-qualification declarations.
Original ZIP, run/job metadata, a runnable audit and byte hashes are preserved
in the immutable packet bound by the [receipt](ci-materialization-hosted-20260913.json).

The external receipt remains blocked at the same two horizontal reactions:
member-feature absolute difference 4.96424095305589e-7 N and prescribed-settlement
difference 3.631256504377234e-7 N. Original absolute/relative tolerances remain
1e-10. This does not resolve the reference arithmetic/integration boundary
recorded in the [isolated OpenSees diagnosis](opensees-corot2d-arithmetic-20260910.md).
No solver or full test suite was executed by this download audit.

A separate pull-request [Repository Python Tests run 34749339137](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34749339137)
at the same source terminated as startup_failure with zero jobs. Its public
GitHub UI reports an unexpected internal error and says errors can be temporary.
That is stronger evidence than the CLI's generic likely-workflow-issue message;
no workflow syntax defect or global service outage is established. Do not treat
this run as a code test failure, successful execution or numerical observation.

The [earlier implementation note](ci-materialization-diagnostics-20260913.md)
left hosted upload unobserved. This observation closes that particular question.
Diagnostic retention is now executed and downloaded, while external comparison,
full-suite execution, independent qualification and roadmap integration remain open.
