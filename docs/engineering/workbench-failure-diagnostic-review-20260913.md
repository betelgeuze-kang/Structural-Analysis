# Workbench review of stored nonlinear failure diagnostics

Workbench now reads the current failed attempt through the authenticated
`failure-diagnostics/{attempt}` route. A 404 preserves the existing service-code
view with no invented work counters. Other retrieval or validation failures
withhold the detailed review. Failed jobs still have no published successful
result/evidence pair or accepted Engineering ResultIR.

The browser bounds both streamed artifacts, verifies original request length and
SHA-256 against the job reference, verifies embedded original result length and
SHA-256, replays the source result hash without rewriting Python number tokens,
and checks request/job/attempt/configuration/authority bindings. Observed counts
must match their individual steps and configured targets. Integer count tokens
such as `3` are distinguished from `3.0`, in addition to rejecting Booleans.
The local worker's compact key-sorted Python JSON is the supported producer
representation; arbitrary alternate JSON encodings are not silently normalized.

For neutral models, original model bytes are checked in the browser. ModelIR's
normalized identity remains verified by the service and linked through the
source adapter receipt; the browser does not claim to independently reproduce
ModelIR normalization. Request v1 has no source revision, so the UI explicitly
shows that label as unavailable. These checks establish transport consistency,
not independent worker authentication or physical validation.

The panel shows attempted, committed, replayed-prefix and newly attempted steps,
recorded history rows, each step's reason and failed-step rollback disposition.
Unknown work remains unavailable rather than zero. A false rollback flag remains
visible as not exact. History rows are explicitly not counts of every solve or
line search, and total API work remains unverified. Buttons download the original
diagnostic and embedded failed-result bytes without reserialization.

The opt-in browser fixture runs one actual public planar 40x-load failure and
stores it through the local worker/service. Both 1280 px and 390 px views show
three attempted steps, two committed steps, eighteen history rows and exact
rollback on the third step. Both original downloads match the authenticated
server bytes. Coherently rehashed wrong totals, floating-point count tokens and
stale-attempt bindings are rejected. Separate adversarial transport cases keep
unknown work and false rollback visible without result authority; these mutants
are never written over the durable solver artifacts.

The diagnostic and existing HTTP/browser tests first passed 11 tests in 33.0 s.
The broader job-loader/transport/status regression selection then passed 52 tests
in 33.8 s. Pinned Node v24.20.0 TypeScript, production build and viewer-delivery
checks passed. Mobile/desktop screenshots and overflow checks exercise the final
panel and original downloads: the final two viewport tests passed in 26.8 s,
and the mobile panel image was inspected. Their output stays separate from numerical
benchmark evidence. The default transport fixture still runs no solver; only
the explicit `--nonlinear-failure` mode executes the real nonlinear test.

A further actual-browser check changed the immutable request's case identifier
without changing its byte length. The review was withheld on SHA-256 mismatch;
that single check passed in 24.1 s. It is additional transport coverage, not a new
physical case or performance observation.

The independent development-contract CI lane now includes the diagnostic
contract, durable failure integration and existing durable service modules.
Its selection grows from 38 to 41 modules, and all 16 workflow-contract checks
pass locally. This adds coverage when external full-suite preparation is blocked;
it does not replace or weaken full-suite or external verification gates.

Publication waited for the preceding `10929befa` development job 103669048394:
951 tests passed in 1061.18 s. Its Native PR Fast run 34736608641 succeeded.
Full Python preparation still failed with `legal_approval=False`,
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. Those preceding-source checks
do not qualify the new UI/CI commit or its expanded development selection.

This completes the bounded current-failed-attempt display and original-download
connection. Historical-attempt navigation, broader producer formats, total
execution-cost accounting, independent verification, source provenance absent
from v1 requests and the full Structural Analysis roadmap remain open. No new
learned benefit, sparse acceleration or release eligibility is claimed.
