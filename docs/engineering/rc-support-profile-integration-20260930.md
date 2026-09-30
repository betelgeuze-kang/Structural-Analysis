# Explicit RC support profiles across local research and durable review

The local persistence, finite-price search and refinement paths from PR #450
now incorporate the saved pin/roller job contract and Workbench review from
PR #469 with complete predecessor history. Both had the same development parent
`3021a69b54d073b6f5dee7e329545bbe4f1237a7`; their original modified paths did not
overlap. Their combination exposed a real cross-layer input mismatch.

A valid explicit pin/roller request passed the durable job contract, then failed
in `DurableRCControlResultSession.evaluate()` with
`rc_fiber_frame_support_count_unsupported`. The quantity calculator had received
the model without the request's support-profile opt-in. This was reproduced
before the correction with a real canonical model and request. No numerical
result was produced by that failed preflight.

Five quantity calls now preserve both explicit request flags: the durable
session, finite-pool price preparation, the initial and refined physical-quantity
checks, and the refined candidate price preparation. The compiler still validates
each model under the declared profile. The existing direct reference evaluator
already forwarded these flags and remains the source of accepted results.
Physical member lengths include overhangs; a support span cannot replace member
length in the quantity or common-price calculation. Quadrature changes must
still preserve the physical quantity basis.

The durable job contract continues to admit the explicit pin/roller profile only
without constant preload. Two fixed endpoints and pin/roller with constant
preload remain rejected before durable execution. Direct local search and
refinement preserve their existing explicit profiles. This integration does not
claim that the durable transport supports every direct API combination.

The regression file `tests/test_rc_control_support_profile_integration.py`
exercises authored small models through actual analysis, fresh reference checks,
reopening and price/screen reevaluation, as well as direct price/refinement
paths. Reused original results carry zero new numerical work and do not receive
new reference-verification credit. The existing full persistence, failure,
authorization, workflow, pin/roller and Workbench suites remain in the validation
scope. The new file is registered in the existing CPU integration job for pytest,
formatting and lint; required repository shards and protection are unchanged.

Validation receipts retain the exact tested commit, executed commands and failed
pre-fix observation. The authored fixtures and synthetic prices establish software
behavior only. They do not demonstrate physical accuracy, learned acceleration,
independent validation, actual hardware latency, commercial price savings or
release approval. The original broader roadmap and constant-preload support work
remain open.

The first complete integration run passed 505 of 506 tests but exposed a real
SQLite WAL-initialization collision in the unchanged simultaneous-same-physics
regression. Connection setup now retries only SQLite BUSY within one monotonic
30-second deadline, closing each failed connection before waiting. It verifies
that WAL was actually enabled and restores the existing 30-second busy timeout
for subsequent transactions. Non-BUSY errors still fail immediately; foreign-key,
FULL synchronous, authorization and transaction semantics remain unchanged.
Deterministic deadline/error/close checks accompany actual reader-lock and
concurrent constructor/submission/single-claim regressions. This correction is
validated with the full affected durable-service and RC suites, not by discarding
the failed observation or loosening the existing concurrency assertion.


## Direct pin/roller design originals in Workbench

A subsequent source-bound review found that the Python v4 section comparison
completed while Workbench rejected its control schema. The design reader now
recognizes the explicit pin/roller profile, binds its API opt-in and authored
control node/component, and checks the horizontal chain, support roles, free
control coordinate and load placement before accepting a verified row. The
shared preload classifier recognizes direct v4 constant loads; durable v4
submission still rejects constant preload. Shared layout/prefix readers preserve
the profile, but the layout-search producer does not yet implement v4 and this
change does not grant that capability.

A single gzip fixture preserves 52 exact Python producer originals (2,513,297
uncompressed artifact bytes; 550,193 packet bytes), with per-file lengths and
SHA256 digests. It includes baseline/narrower comparisons with no preload and
with direct preload, plus actual invalid restrained-control and support-preload
failures. Existing fixtures are unchanged. Both valid comparisons keep fresh
full-reference results, 1.9 m physical member length including overhangs,
46.17684 kg of authored longitudinal steel and the same synthetic common-price
basis. The 4.56 estimate difference is regression arithmetic only.

Failed producer rows retain their quantities, invocation outcomes and original
errors, with unknown work still visible and selection disabled. A model check
applies to verified rows, so an invalid model cannot become a positive accepted
result, and its original failure remains reviewable. Desktop/mobile tests import
these originals and compare downloaded bytes; rehashed profile, opt-in, control,
reaction, load, quantity and member-price contradictions remain rejected. These
browser routes serve saved originals. A live HTTP pin/roller worker-to-Workbench
execution and actual device response-time budgets remain open.

## Rejected idempotency conflicts create no request blobs

The authenticated HTTP submission path previously published a content-addressed
request blob before deciding whether its tenant/key already identified another
request. One valid request, one exact retry and three distinct conflicting
requests returned 202, 202, 409, 409, 409 but left four request blobs after service
reopening. Only one job/event/budget row existed and no solver was invoked;
6,873 logical bytes (12,288 allocated bytes) were unreferenced conflict output.

The existing SQLite immediate transaction now decides the immutable key binding
before publishing a request blob. Concurrent different requests for one key have
one winner and one rejected conflict. Exact retries still check stored-blob
integrity and repair a missing blob; corrupt blobs remain rejected. The same
HTTP sequence now leaves one blob before and after reopening, with zero new
conflict bytes and no solver invocation. Publication runs under the existing
writer lock; authentication, immutable request hashing and job authority remain
unchanged. This fixes this rejection path. It neither deletes historical orphan
files nor establishes complete filesystem/SQLite atomicity or a production disk
quota. Those storage and operating-budget obligations remain separate.
