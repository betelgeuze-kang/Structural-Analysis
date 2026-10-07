# Durable job store backup and recovery

These commands are for the local operator who owns the entire single-host store,
including every tenant. They are not a tenant-facing export API. Use an installed
Python environment that contains this version of `structural_analysis`.

## Back up to a new directory

```bash
python -m structural_analysis.execution.job_store_backup_cli backup \
  /path/to/job-store /path/to/new-backup \
  --maximum-bytes 1073741824 --maximum-files 10000 --timeout-seconds 60
```

The numbers above are example operator-selected bounds, not recommended capacity
or whole-job disk/RSS limits. The command reserves the SQLite writer boundary;
if another writer already owns it, the command fails without waiting indefinitely.
It copies a committed SQLite snapshot (including WAL data) and content-addressed
blobs. Configuration, authorization configuration, locks and unrelated root files
are not exported. A backup can briefly block cooperating service writers.

On exit zero, retain `manifest_sha256` from the JSON response separately from the
backup directory. Hashes detect different bytes; they do not authenticate a
compromised operator or storage host. Backups may contain private project data;
the destination is created with owner-only directory/file access.

## Verify a sealed backup without restoring it

```bash
python -m structural_analysis.execution.job_store_backup_cli verify \
  /path/to/new-backup \
  --manifest-sha256 REPLACE_WITH_THE_SEPARATELY_RETAINED_DIGEST \
  --maximum-bytes 1073741824 --maximum-files 10000 --timeout-seconds 60
```

Verification takes no destination and writes no receipt into the backup. Save its
JSON output separately if an operator record is needed. It checks the separately
retained manifest digest, every listed member's bytes, database integrity and
stored references. Pending markers and SQLite WAL/journal sidecars are rejected;
this command is for a sealed, quiescent backup, never a live store. No other process
may modify that backup during verification. SQLite reads its verified main file
in immutable read-only mode without creating sidecars. Unlisted unrelated files
are not admitted or inspected. A passing receipt covers storage integrity only;
restore and the service's application checks are still separate steps.

The verification response includes aggregate job-state counts and the number of
recorded worker leases, without job identifiers or token material. These are
snapshot facts: expiry is not evaluated, and the checker cannot establish that
original writers have stopped. A backup of running jobs retains those leases.
Before routing work to a restored store, fence the original service and workers
through the approved operational procedure. A lease copied to two independently
active stores cannot prevent duplicate execution across them. On the recovered
single store, existing claims remain unavailable until their saved expiry; a later
claim uses the service's ordinary expiry/requeue transition and a new lease token.
An old token is then rejected. Never edit lease rows to skip that procedure.

The snapshot also retains the root's immutable blob payload cap and each RC job's
consumed invocation reservations. Recovery does not replenish an exhausted job
budget; reopening with a conflicting payload cap is rejected. These are the
existing application limits, not guarantees for total disk/WAL/inodes, memory,
CPU time or duplicate work across two independently active restored copies.

## Restore without activating a service

```bash
python -m structural_analysis.execution.job_store_backup_cli restore \
  /path/to/new-backup /path/to/new-restored-store \
  --manifest-sha256 REPLACE_WITH_THE_SEPARATELY_RETAINED_DIGEST \
  --maximum-bytes 1073741824 --maximum-files 10000 --timeout-seconds 60
```

The destination must be new and outside the backup. Keep it unused throughout
recovery; do not concurrently start a service against it. Restoration verifies
member paths, lengths, content hashes, database integrity and stored artifact
references. It never overwrites a live store, changes stored leases, starts a
worker/server, or changes routing. Credentials must be supplied separately using
the existing deployment's approved configuration process.

A successful restore writes `restore-receipt.json` and removes its incomplete
marker. Only then may the operator explicitly open that new root with the service
and run the existing per-job `validate_integrity` checks using the appropriate
tenant authorization. Application/engineering integrity is not asserted by the
backup command. Reconcile recovered active jobs and lease expiry before allowing
workers to resume. Switching a live deployment is a separate operational action.

## Failure and retry

Nonzero exit leaves any new partial destination for inspection. Do not activate
it or delete its marker to bypass checks. Fix the cause and choose a new destination
for the next attempt. The service refuses roots containing any of these reserved
names (including dangling links):

- `.job-store-backup.pending`
- `.job-store-restore.pending`
- `backup-manifest.json`

The first two identify incomplete operations; the last identifies a sealed backup
that must not be mutated by opening it as a live service. A restore completion
receipt can coexist with a pending marker if finalization failed; the pending
marker takes precedence. The CLI reports bounded generic errors without printing
underlying database/path exceptions. Interruptions do not activate the target.

This implementation assumes a trusted local filesystem and cooperating writers.
It does not prove power-loss recovery, arbitrary hardware-failure handling,
protection against concurrent hostile path replacement, distributed backup,
whole-filesystem quotas, or independent physical correctness. Payload/file/time
checks are cooperative; an operating-system I/O call can exceed a time deadline.
