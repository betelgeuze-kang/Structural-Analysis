# Source-bound external receipt integration

This local integration combines the planar attempt records from PR #479
(`0f7149717156c75e41f44e21beae53b09b327b7a`) with PR #517
(`e6a9c7c030b3e0dd5c796ec1fd2c61c94cc8c80c`). The replay comparator first
validates each stored and current metric against its own primitive responses
and declared tolerances, then compares primitive responses, absolute error,
identity, tolerances and pass flags. Only redundant cross-environment relative
error comparison is omitted. Rejections retain the first mismatching field path.

The planar driver still stops at the first failed attempt and requires every
authored load factor before accepting a complete path. Both the attempt
completeness check and replay mismatch diagnostic are retained. The numerical
acceptance tolerances and source checks are unchanged.

All existing same-operator host/container artifacts retain their original bytes
and declared execution sources. The fresh host receipts for `84602ccf9`,
`4b6ee9183` and the separately retained PR #517 run on `cf679f9a8`, plus the
clean-runner packet for `170b703d2`, describe those historical executions.
Combining their code does not turn those receipts into a fresh execution of
the integrated source or transfer container parity to it. The saved current
product replay still describes reused external results. Protected productization
evidence and gap ledgers are unchanged.

Validation of each published integration source requires: complete receipt,
planar-attempt, clean-runner and profile-state regressions; a separate fresh
OpenSees/CalculiX execution and strict current-source receipt check; preservation
of committed input hashes, all planar attempt rows and original artifact bytes;
and the required hosted checks. Historical and fresh receipts must remain
separate, and any temporary CI-style replay materialization must be accounted
for and restored after validation. No new execution or passing test is claimed
by this integration note. Independent operation, legal approval, wider physical
validation, Verification Level 2 and release authority remain open.
