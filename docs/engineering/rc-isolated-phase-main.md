# Isolated durable RC phases

An optional authored `execution_config.phase_execution_policy` specifies the
analysis and verification timeout in milliseconds (1..3600000 each) and the
termination grace (1..5000). All fields, exact integer types and schema version
are required. The policy participates in the immutable job/request/restart
identity. Absent-policy requests retain their existing inline execution.

For an opted-in Linux job, the durable parent reserves each API invocation and
retains credentials, heartbeat, checkpoint and publication authority. A fresh
interpreter reconstructs the original request/restart and performs either the
analysis or its mandatory fresh verification. The child receives bounded
binary frames, not credentials or the parent's loader environment. Entry-module
source hashes and input identities are checked. This is not an attestation of
all transitive code or a filesystem sandbox.

Launch, imports, reconstruction, API/export and transport fall within the phase
deadline. A timeout or observed heartbeat failure terminates the owned process
group and requires observed direct-child reaping. Linux parent-death protection
and a parent-identity recheck cover the direct child if its worker dies before
or after arming. Lost, malformed, late or unmeasured replies leave the reserved
ordinal unknown; they cannot advance the last verified prefix or refund budget.
A stale worker cannot mutate its replacement lease. A measured API exception
retains its original structured report and timing.

Unsupported platforms and nondefault SIGCHLD reject before reserving or
launching a phase. Competing reapers and cleanup errors remain explicit; they
cannot manufacture a successful child exit. The parent must exclusively own
child wait operations. Same-group descendants are covered, escaped descendants
are not. Process creation or uninterruptible kernel teardown can exceed the
nominal deadline; this is not a hard whole-worker wall-time guarantee. Heartbeat
failure is acted on after it is observed, not instantaneously at remote expiry.

Transport byte limits are not RSS, disk or CPU quotas. Child API/export timings
are separate from parent launch/import/IPC/reaping and durable-storage costs;
no total-cost benefit is claimed. Cross-store duplicate prevention still requires
stopping the original before activating a restored copy. No cgroup allocation,
whole-host resource guarantee or physical validation is introduced.

## Integration and evidence

Ported the phase policy, supervisor, bootstrap and scoped worker integration from
`42b5a840966210ff0c0528034a2b8a4b507fd46c`. Current strict-JSON imports, immutable
chunk contract and checkpoint lease-release semantics are retained. Unavailable
donor assembly reuse/constant-loading features are not imported as dependencies.
The current contract accepts only the new phase policy in addition to its two
existing execution fields. The caller cannot set a custom child entry or environment.

Tests exercise real subprocess timeout/KILL, ordinary group descendants,
parent SIGKILL, competing reapers, malformed/oversized/late IPC, missing/malformed
source timing, bounded stderr, setup-failure pipe cleanup, and authority loss.
Worker lifecycle tests preserve the exact earlier prefix and unknown ordinal.
Current-source numerical comparison runs the three-target reversal inline,
isolated full-path, and isolated across three fresh service instances; their
terminal native checkpoint bytes match, with fresh verification for each chunk.
No retained numerical fixture shortcut is used for that comparison.

The backup integration matrix covers inline/isolated execution crossed with
uncapped/10 MiB retained-payload policy: actual calculation, checkpoint backup,
original worker stop/reap, restored worker completion, report, second backup
and read-only numerical reopen. Five spent reservations and unknown ordinal 3
remain, as does the persisted cap. These are synthetic RC software lifecycle
checks; public-source specimen qualification is a separate unmet requirement.
