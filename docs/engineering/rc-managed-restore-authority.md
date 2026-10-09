# Managed RC restore authority (development)

This implementation is for cooperating Linux processes on one trusted host.
Keep the authority directory outside every job store and backup. Its generation,
active root, and reservation journal are shared by all copies. Never copy or
recreate that directory to make a restored store executable. Missing authority
state is an error. Distributed execution and hostile administrator fencing are
not provided.

New managed stores can be enrolled through `JobExecutionAuthority.create` and
the `DurableJobService` constructor's `execution_authority` and
`execution_binding` arguments. Enrollment requires a new destination and uses a
staged, no-replace installation. Existing unmanaged stores are rejected; an
offline adoption procedure is still outstanding.

## Restore and explicitly activate

Use the existing backup/verify/restore command with a separately retained
manifest digest. Restore into a new directory. A restored managed store rejects
ordinary opening because it still carries its original root binding.

After the managed numerical workers and their children have stopped, activate
the restored copy:

```sh
PYTHONPATH=src python3 -m structural_analysis.execution.job_managed_restore_cli \
  /path/to/sealed-backup /path/to/restored-store \
  --manifest-sha256 RETAINED_DIGEST --maximum-bytes 100000000
```

For a backup from an earlier authority generation, also supply the exact current
`--expected-generation` and `--expected-root`. A stale expectation is rejected.
The command does not start a service, change leases, or refund reservations.
Existing restored leases retain their ordinary expiry semantics.

Activation takes the authority's exclusive nonblocking lock. An active managed
worker holds a shared lock through calculation, publication and child cleanup;
isolated numerical children inherit the descriptor. Activation therefore fails
while those holders remain alive. Arbitrary escaped descendants are outside this
contract.

The destination is checked against the sealed backup before switching. The
external generation commits first, fencing the old root. The destination binding
commits second. If interrupted between them, both roots reject execution. Retry
the same command, backup, destination and expected binding to finish; preserve all
state. An already completed activation returns `already_activated`, which only
confirms the binding and does not requalify subsequent mutable application data.

## Budget and evidence

Each invocation consumes an external reservation before the local event commits
and before numerical work begins. A crash between those steps does not refund
the reservation. Claim, budget read and explicit reconciliation import missing
ordinals as unknown work, without inventing a worker lease or numerical outcome.
Actual reservations retain their global ordinal even after imported gaps.

Activation checks sealed bytes, SQLite structure and references; it reports
`application_integrity_checked: false`. Service application validation, numerical
verification and report bindings remain separate checks. Tests cover old queued
and checkpointed snapshots, conservative spend, process death during cutover,
reopening and quantity-report reads with synthetic RC inputs. They are not
independent specimen validation, a total-host resource guarantee or release
qualification. Publication review and the wider readiness gates remain open.
