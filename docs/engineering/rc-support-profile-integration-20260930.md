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
