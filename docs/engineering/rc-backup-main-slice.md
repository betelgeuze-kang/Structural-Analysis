# Operator backup and RC worker recovery on main

This slice ports the existing local-operator backup/verify/restore tools from
PR #450 source `42b5a840966210ff0c0528034a2b8a4b507fd46c` onto main's current RC
service. It does not bring the draft branch's unrelated solver, AI, or protected
evidence changes. The failure-diagnostic table is optional on main; if present,
its references are checked. Core RC tables remain mandatory.

## Operator procedure

Use `python3 -m structural_analysis.execution.job_store_backup_cli` with one of
`backup SOURCE NEW_BACKUP`, `verify BACKUP`, or `restore BACKUP NEW_STORE`.
All commands require `--maximum-bytes`; file and time bounds are configurable.
Retain the successful backup's `manifest_sha256` separately and supply it using
`--manifest-sha256` for verification/restoration. Never obtain the trusted digest
from an untrusted replacement manifest. These digests detect changes relative
to retained bytes; they do not authenticate an experiment or source author.

Backup serializes cooperating database writers and captures committed WAL data
using SQLite's backup interface. It preserves content-addressed blobs, historical
references, execution reservations, and report revisions. Only new external
paths are accepted; existing destinations are never overwritten. Partial outputs
are retained with quarantine markers. Service initialization rejects incomplete
destinations and sealed backups before modifying a database. Verification does
not start a service or modify the sealed backup.

Before starting a restored store, stop the original service and every original
worker and retain it offline. Restoration does not fence the source, revoke
source leases, rewrite execution budgets, or implement a live failover. Independent
copies can both claim the same job if an operator starts both. Expiry and stale
token protection apply within a single store. Automatic exclusive activation
remains a separate P1 gap; this procedure must not be described as distributed
or automatic recovery.

## Evidence and limits

The integration test calculates the first RC target in a child worker, snapshots
its retained checkpoint and unknown reserved attempt, kills and reaps the
original worker, restores into a new root, resumes in a fresh worker after lease
expiry, and completes the second target. It checks same-store duplicate/stale
lease rejection, five preserved reservations with unknown ordinal 3, then backs
up and reopens the result and quantity report byte-for-byte. Read-only reopen is
tested with numerical entry points forbidden.

The backup integration now runs for both the cantilever request and the
explicit fixed-guided axial v5 request. It additionally checks that restoration
preserves the immutable request content hash. The two backup cases and four
fixed-guided public/lifecycle cases passed together (6 tests). These checks
exercise separate-store backup recovery rather than only restart in place.

The model and prices are synthetic test inputs. This is software workflow proof,
not a real specimen comparison, actual construction estimate, or release proof.
Process exit is not an OS-wide RAM/CPU ceiling or descendant-process guarantee.
Payload/file/time bounds are cooperative and do not establish filesystem quotas,
hard I/O deadlines, power-loss durability, remote replication, or original-writer
fencing. Sealed-container verification leaves `application_integrity_checked`
false; retained results still require the service's application-level validation.

## Concurrent processes in one store

`test_rc_process_reservation_race.py` starts four fresh interpreter processes
behind a barrier. Exactly one claims the queued RC job. Four further processes
then race twelve reservation requests under that lease: ordinals 1 through 8
are issued once each and four requests are rejected at the configured limit.
A fresh service instance retains all eight reservations. No solver is invoked;
reserved work remains consumed even without a numerical outcome. This verifies
single-store atomicity and does not close the independent-copy activation gap
above. The race and RC service tests passed together (66 tests).
