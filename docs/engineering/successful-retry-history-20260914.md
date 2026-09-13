# Actual successful retry with preserved failure history — 2026-09-14

Source head `17010d495d651d3d53407db4dfc7b9dcee0867ad` plus the sealed fixture,
browser-test and CI patch. Production solver and Workbench code are unchanged.

The new explicit `--failure-history-success` test mode uses the ordinary planar
portal loads. During attempt 1 only, the Newton linear-backend function raises a
controlled `LinAlgError` exactly once. The real numerical error handling, worker
and durable service record a blocked result, fail the job and retain its original
failure diagnostic. This is an injected backend outage, not an independently
observed structural singularity.

After the scoped patch exits, the service resumes the same job. The fixture
asserts that attempt 2 has byte-identical request input. The unpatched solver
executes it successfully, and the actual durable job view becomes `succeeded`
with original result/evidence references. No job status, artifact reference or
successful result is fabricated. Attempt 1's diagnostic remains byte-identical.
This advances the earlier synthetic-succeeded-view coverage to an actual local
worker/service transition under controlled fault injection.

## Browser and CI verification

Two new actual loopback HTTP browser tests use desktop and 390-pixel widths.
They verify the current engineering ResultIR, explicitly review failed attempt 1,
download the original diagnostic bytes, and confirm that the current succeeded
job and verified result remain unchanged after reviewing/clearing history.
Attempt 2 cannot be selected as a previous failed attempt. The screenshot review
shows the earlier attempt labelled as diagnostic-only, with exact rollback and
zero committed steps, separate from the current successful result.

The initial browser run passed all 8 tests in about one minute. After strengthening
the one-outage and identical-request assertions, the final combined new/previous
history suites again passed **8 tests in 1.0 min** (runner interval 61.948952948 s).
Each suite reuses its service fixture across browser views; eight tests are not
eight independent structures. The older synthetic changed-checkpoint test remains
explicitly synthetic. No changed-checkpoint end-to-end success is claimed.

Pinned Node 24 TypeScript checking, Ruff and `git diff --check` pass. The new
browser spec is registered in the actual HTTP CI step; its focused workflow
contract test passes (1 passed, 17 deselected). Hosted execution of this addition
is still pending. The browser used the existing built frontend; no fresh build
or production deployment is claimed for this test-only change.

The [receipt](successful-retry-history-20260914.json) binds source snapshots and
patch, runner, final log, initial/final browser outputs, original diagnostic
attachments and screenshots. The read-only packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-successful-retry-7_rtyj91`:
19 files, 738012 bytes. Adjacent `.inventory.json` SHA-256:
`6b3d1dffe87a3036b83282ff141d29f106aa03b1db029a5263f2a295229e4833`.
All file lengths/hashes were reread before sealing. The runner interval includes
fixture startup and browser execution; it is not a complete research-lifecycle
cost, a production recovery-time guarantee or a numerical speedup.

This closes the bounded local successful-retry/history scenario under injected
backend failure. Independent physical validation, real operational incidents,
changed-checkpoint history, full user-task costs and broader M5 acceptance remain
open. Historical failed results never acquire current-result authority.
