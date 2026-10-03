# RC generation work summary contract — 2026-10-01

The authored full-training driver now keeps failed generation rows in its cost
accounting. A row without a comparison report cannot turn unknown work into a
known zero or allow the next stage to reuse the native-call budget.

The previous driver at c4de581b9f261d9d53164a4ad827fac84be0f989 discarded those
rows before recounting the available comparison reports. Its shared counter
also iterated only the keys present in each work record, so a missing required
counter could retain the initial zero while reporting unknown_work=false.

The summary now retains available nonnegative integer counters for core calls,
Newton iterations, and actual linear solves. Missing reports, records, required
keys, malformed containers, invalid counter values, or non-Boolean completeness
flags leave unknown_work=true. Unavailable work is not inferred or repaired.
This shared counter also protects the label and complete-path progress summaries.

Generation additionally preserves unknown flags from the producer aggregate,
the individual rows, and the comparison reports. The aggregate must match the
available original-report recount with exact integer types. Missing, duplicate,
or foreign TRAIN case outcomes prevent readiness even when a cached sample file
contains all 20 samples. Inconsistent aggregates yield HOLD/unknown; the original
producer report and its hash remain unchanged, while the convenience result
keeps the available original-report counters.

A completed seed fit cannot excuse unknown native work. Conversely, a recorded
physical failure or failed fit can yield HOLD with known native work: fit
uncertainty remains separate. Normal binary64 and retained-profile receipt
fixtures keep the ready contract.

The complete driver test module passed 73 tests with no failures, errors, or
skips. The tests forbid structural solves, material integration, and policy
fitting; authored policy codec and report fixtures provide no numerical,
learning, physical, or performance evidence. Ruff and diff checks passed on the
same source. The tested driver SHA256 is
72ee8938d71336608419788a149fd7a98ce736c2ea44879fab6bb24f07b09ff8.

The initial regression probe reproduced three missing-counter failures in the
old implementation. Two generation cases stopped in fixture setup because the
temporary parent directory was absent; those setup errors are not product
failures. The original failure log and JUnit remain preserved separately from
the successful complete-module run.

The E05 campaign remains completed on its original cd74 source and is not
restarted or relabelled as this implementation. Its 18 internally verified
comparisons, zero learned proposals, negative online cost result, and unavailable
whole assembly/material counts are unchanged. A stronger summary boundary is
not proof of AI acceleration, external source admission, independent physical
validation, hardware qualification, or release readiness.

Local receipts and reviews are retained under the separate
generation-unknown-work-followup-20261001 packet in the PR backlog evidence
directory. Hosted results remain attached to their exact commits; predecessor
CI success does not qualify a subsequent publication.
