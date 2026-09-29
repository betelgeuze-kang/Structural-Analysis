# Hosted receipt for 90cc21dcd

Exact tested revision: `90cc21dcd3885601bae9d3769bc71961eeb5456d`.

- [Repository Python](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35482427573): development job `106002507007` passes **1,677 tests in 1,058.91 seconds**; collection passes. Full shards fail during evidence preparation, so the workflow fails. Shard 3 (`106002507170`) records `external_code_to_code_product_replay_not_passed` and `external_code_to_code_technical_receipt_not_ready`; its actual full repository test step does not run.
- [Frontend](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35482400507): job `106002431245` executes **812 tests: 810 pass and two fail**, in 18.0 minutes. Separate seven-test browser setup passes. This includes the newly registered default Workbench files; the optional Python-backed lane is not implied to have run.
- Both failures are the existing L-frame 1440px/390px browser cases. The failure site is the final `panel.screenshot`, after original report validation, quantities/plasticity display, selection, byte-exact result download and viewport bounds assertions. The enclosing test's 30-second timeout expires. The desktop log shows waiting for element stability; the mobile log records page/context closure on timeout. These are real CI failures, not a successful frontend gate.
- Workflow Contract `35482400505` and P0 Canonical Verification Contract `35482400499` pass. Ordinary CI `35482400498` fails. Every run is terminal before the subsequent development publication.

The subsequent L-frame browser tests receive a scoped 60-second test budget,
consistent with other long artifact-validation browser cases. Assertions,
screenshots and physics tolerances remain intact; no automatic retry or skipped
test is introduced. Later local checks and new-head CI must be reported separately
from this failed exact-head run. Hosted elapsed times across commits are not
controlled performance measurements. Full-suite, external acceptance and release
remain incomplete.
