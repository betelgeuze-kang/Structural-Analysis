# Internal corotational control with fixed nodal loads

A cyclic column experiment can hold axial load constant while the lateral reaction changes sign. Putting both components into the reference load vector changes both with the solved load factor. `StatefulCorotationalFiberFrame2DProblem.fixed_external_loads` supplies dead nodal forces and moments in global coordinates, independently of that factor.

The assembly uses `F_external = F_fixed + lambda * F_reference` plus existing member load contributions. Fixed loads contribute to equilibrium and reactions but not to the load-factor derivative or displacement tangent. Their direction does not follow the rotating member. Nonempty fixed-load definitions are bound into the problem contract hash; checkpoints cannot be restored against a changed definition. Empty fixed loads preserve the previous problem fingerprint.

The epoch-zero checkpoint is a constitutive seed, not a claim of equilibrium under fixed loads. Solve a load step at factor zero to obtain the preloaded state before the control history. The direct path accepts that state as `initial_checkpoint`. `allow_reversal=True` explicitly permits changing displacement direction; its default remains false. Consecutive identical targets remain rejected. Checkpoint restoration still requires the caller's same problem, including its fixed loads.

Regression covers constant axial load through lateral load-factor sign changes, initial equilibrium, finite-difference tangent and load-factor columns, exact failed-step rollback, changed-load checkpoint rejection, and byte-identical serialized restart. A synthetic concrete-damage/steel-plasticity column reaches positive and negative 10 mm with 50 prescribed increments and reproduces its terminal state after restart. The coarse five-target path can fail line search and must preserve its last committed state; convergence improvement is allowed, so the test does not require failure forever.

The internal `run_corotational_control_subdivision` runner retries a failed increment by bisection. Every solver attempt, including a failed one, spends its invocation budget. Successful intermediate states remain committed; depth, attempt and floating-point progress limits stop the path while preserving the last accepted state. Input collection is bounded to reject unbounded target streams before solving. Regression compares the accepted subdivision history with direct replay and requires byte-identical terminal checkpoints.

Set `attempt_limit_per_call` to pause cooperatively after a bounded number of solver calls. The result includes `continuation` bytes containing the original and accepted checkpoints, pending subdivisions, completed authored targets, cumulative attempt count and terminal failure reason. Supply those bytes as `continuation` with the same inputs to resume. A completed or exhausted record performs no extra solver work. The cumulative cap is `maximum_attempt_count`; the per-call limit does not reset it.

Restoration checks the artifact checksum, strict JSON schema, checkpoint state, pending queue and counters. The context binds authored targets, controlled degree of freedom, solver settings, subdivision depth, total budget, problem identity and every Python source file in the solver package. A source or policy change requires a new run. The checksum detects accidental damage, not deliberate rewriting with a recalculated checksum. Restoring an older valid record can replay work: a managed, durable authority must reject stale records and reserve attempts before execution. This runner alone does not provide that authority or account for a process killed during an unfinished attempt. The source-replayed API and durable service below add separate artifact and reservation custody.

Repeated-target semantics and the complete public RC project/report workflow remain open. The synthetic material values are not measured specimen inputs. This does not establish independent physical validation, design authority, general failure prediction, or release readiness.

## Canonical model bridge

`compile_rc_corotational_control_model` validates a detached canonical model through the existing RC geometry/material compiler, then constructs corotational members using the same sections, identifiers and integration rules. Supported support profiles retain their explicit opt-ins. Unsupported geometry or material semantics remain rejected before solving. The returned binding records the canonical model and source input checksums.

Model loads remain proportional. Additional `fixed_nodal_loads` rows use `(node_id, FX/FY/MZ, value)` with forces in kN and moments in kN*m; duplicate rows, unknown nodes, unsupported components and nonfinite values are rejected. The function does not infer an axial load from experimental response data. A zero-factor preload and subsequent cooperative continuation can use the compiled problem, including after re-reading the model. Preload solves are separate from subdivision attempts and must be reserved and counted separately by the managed workflow.

The legacy durable RC worker continues to validate small-displacement artifacts. The separate corotational API and v6 worker described below preserve their own source and result contracts. Managed restart and saved nodal reporting have the bounded software qualification described below; a complete public specimen workflow remains open. Compilation does not inherit the small-displacement J1–J5 engineering authority.

## Source-replayed result artifacts

`analyze_rc_corotational_control` accepts the canonical model, named control node/component, full authored targets and explicit fixed loads. It establishes factor-zero preload, runs bounded subdivision, and exports canonical result bytes plus continuation bytes. Accepted response rows retain node identifiers, displacement triplets (m, m, rad), external/reaction triplets (kN, kN, kN*m), member responses and parent/child checkpoint hashes. The history includes preload and accepted intermediate increments. Failed control work remains in the attempt count.

A restart first replays the complete prior control prefix from a fresh preload and requires byte-identical continuation before advancing. Rewriting a checksum or spent count cannot substitute an unverified prefix. Preload calls, prefix replay calls and new control calls are reported separately. A valid older prefix can still be replayed; only the managed authority can reject stale records or prevent duplicate invocation. Exceptions after execution begins report partial work as unavailable instead of zero-cost success. Result byte limits also bound accumulated response export.

`validate_rc_corotational_control_artifacts` reruns the caller's request and compares complete canonical result and continuation bytes. Its replay costs are separate from analysis costs. A matching paused or blocked artifact can pass artifact integrity while remaining incomplete. This same-solver replay does not provide independent physical validation or code approval. The worker records invocation wall/CPU time and reservations; memory bounds, isolated-child interruption and managed process-death recovery remain separate integration requirements.

## Durable request prerequisite

`validate_rc_corotational_job_request` freezes the v6 request before numerical execution. The request names the complete canonical model, controlled node/component, authored target history, additional fixed loads, full solver settings, declared source revision and independent control/API invocation limits. Extra fields and ambiguous JSON numeric types are rejected. Returned model objects and dictionaries are detached from the immutable bytes. The source revision is a caller declaration, not proof of executed source.

Progress is explicitly measured in control solver attempts and has an immutable maximum cap. Completed authored targets and successful terminal completion remain separate quantities; a successful path may finish before consuming its attempt cap. The request decoder supplies the service admission and worker integration below. Its own checks are pure input validation and do not execute or qualify the numerical path.

## Durable service and worker integration

The service admits v6 corotational requests and reserves each analysis and fresh numerical verification invocation before the call. Worker publication compares its claim with the live lease, renews that lease independently, records invocation timing/work, and binds checkpoint/result receipts to the actual persisted outcome pair. A checkpoint advances actual cumulative control attempts, including failed increments used for subdivision. Reopening a store and using a different authorized worker reproduces the continuation. A stale lease cannot publish, and altered checkpoint bytes are rejected before another reservation. An insufficient verification budget cannot publish success.

The new attempt-based JobView uses `structural-analysis-job-view.v2` and `progress.unit=control_solver_attempts`. Successful completion retains actual consumed attempts below the immutable cap, rather than filling the cap as if all attempts occurred. Existing v1 views and target-based job semantics are unchanged. The v6 result also retains authored target completion separately. The old small-displacement quantity-report endpoint remains explicitly unsupported for this distinct result type.

The integrity check reads job state, events, budget and outcomes in one database snapshot, so a concurrent lease renewal does not look like damaged history. The v6 check binds mutable attempt counters to the immutable request, submitted cap, latest checkpoint event and completed result event. Retained checkpoints are checked against their own earlier progress while completed jobs use the final result progress. Receipt custody is rechecked against recorded invocation outcomes without executing another solve. Changing only a SQLite counter or dropping the retained checkpoint is rejected even when all artifact hashes remain intact.

Pure service validation checks transport, immutable request/source declarations, native state codecs, saved prefix custody, and trusted-worker numerical replay attestations. It does not run the solver itself. Synthetic receipt tests are transport evidence; the separate actual tiny model test performs the analysis and mandatory fresh verification calls. These tests do not establish an actual public specimen comparison.

The worker spans the service's `execution_guard`. Linux workers also acquire the per-job permit described below. Unmanaged custody stays within the canonical root; explicitly enrolled Linux managed stores retain external generation/root binding and conservative reservation custody. A tiny-model integration test checkpoints two control attempts, makes a backup, spends an unrecorded third invocation, activates the restored generation and rejects the old root. Resume consumes invocations four/five and completes three control attempts under the original cap of 255, with the unknown third reservation preserved and total invocation spend five of six. Cutover attempts inside actual analysis and replay are blocked for the worker lifetime.

The single-host managed restore test is separate from process lifecycle evidence. Memory/resource limits, arbitrary orphan reaping, the Workbench corotational report flow and release readiness remain unqualified. A changed package source requires fresh source-bound continuation evidence.

## Opted-in isolated numerical phases

`structural-analysis-job-request.v7` keeps the v6 model, numerical settings, budgets and result contract and requires `execution_config.phase_execution_policy`. The v6 execution-config shape remains unchanged and continues to use in-process numerical calls. A v7 execution config can be authored as:

```json
{
  "attempt_limit_per_call": 2,
  "maximum_api_invocations": 6,
  "phase_execution_policy": {
    "schema_version": "bounded-rc-corotational-phase-execution-policy.v1",
    "analysis_timeout_ms": 60000,
    "verification_timeout_ms": 60000,
    "termination_grace_ms": 500
  }
}
```

Timeouts must be integers from 1 to 3,600,000 ms and termination grace from 1 to 5,000 ms. Extra fields and boolean, float or exponent spellings are rejected. The policy is part of the immutable job/restart binding and is excluded from numerical API arguments. Authored inputs keep the whole target history; the supervisor does not turn a restart into a sliced history.

After host and managed-descriptor validation, each analysis and fresh verification reserves its invocation before launching a separate isolated interpreter. The parent retains credentials, lease custody and publication. The child arms Linux parent-death protection before package imports, reconstructs the original request/native restart, and uses a separate bounded binary namespace. Request/native segments are capped at 16 MiB, result/report segments at 64 MiB, and total binary segments at 112 MiB. These are transport limits rather than memory or disk quotas.

An authored deadline covers parent request preparation, child launch/import/API/export, transport and direct-child cleanup. Successful transport requires observed exit status zero and exclusive direct-child reaping. The stored invocation separates measured child API/export wall/CPU time from total supervisor wall time. The latter includes launch/import/transport/cleanup and is not a CPU or RSS measurement. A measured child exception retains its error type and available partial-work counters.

Timeout, missing/corrupt/late transport, rejected return or cleanup failure produces a raised audit outcome with `phase_supervision.status=unaccounted`, `process_cpu_ns=null`, and available cleanup diagnostics. Its reserved invocation remains spent. Such an outcome cannot enter an accepted result receipt. The durable outcome blob and event hash retain the full supervision record; the compact result receipt does not independently hash that entire record. Tenant access to `read_rc_invocation_artifact` retrieves the bound original outcome.

Claim, heartbeat and failure transitions check current time after obtaining the database transaction lock. The worker's lease keeper starts from the last confirmed lease and checks both service-clock expiry and a conservative monotonic deadline without waiting for a pending database renewal. Observed expiry remains latched. A v7 supervisor then stops and reaps its child when that parent check fails. An ordinary in-process v6 call cannot be cancelled by this check.

Tests distinguish real tiny numerical analysis/fresh verification from controlled subprocess lifecycle cases. Controlled children test cutoff, owned-group termination, direct-child reaping, malformed replies and inherited guard release without claiming numerical execution. The managed guard spans child cleanup, heartbeat shutdown and publication. Parent-death protection covers the direct child; ordinary group cleanup covers same-group processes during an observed failure. Escaped descendants and a hard memory quota require separate qualification. Exact-main Nightly, public specimen initial state/material correspondence and the complete Workbench report flow remain independent completion gates.

## Per-job execution admission

Cooperating Linux RC workers acquire an exclusive nonblocking job permit inside the managed generation guard, before the worker heartbeat, reservations or numerical calls. A busy permit returns `job_execution_permit_busy` without failing or modifying the replacement claim or spending another invocation. The caller can retry the still-valid claim after the previous execution releases its permit; an expired retry must acquire a new claim. Different jobs use independent permits.

Managed permit files are keyed by job ID in the external authority and retain that identity across backup activation and restored generations. Device/inode pins for the directory and each job file live in the authority database. Unmanaged permit pins live in the job database and belong to one canonical root; a restored unmanaged copy has independent custody. Backups copy database/blob artifacts and exclude runtime permit files. Permits are persistent runtime state: never unlink or recreate their files during cleanup. Missing, replaced, symlinked or multiply linked objects are rejected. New managed authorities initialize this namespace explicitly; an older authority without pinned permit metadata requires an explicit migration before protected execution and is never silently repaired. Its completed artifacts and checked reservation history remain readable under the original generation binding without creating permit metadata. New registration, reservations and numerical admission stay blocked until migration; partial permit metadata, stale generations and invalid reservation journals remain rejected.

The parent holds the permit through numerical execution, result or failure handling, direct-child cleanup and heartbeat-thread shutdown. Both generation and job descriptors are inherited by each opted-in numerical child. Closing the parent's copy does not unlock a surviving child's open-file description. If the worker is killed before the child arms its parent-death signal, the inherited descriptors keep a replacement and generation activation excluded until the bootstrap detects the dead parent and exits. If the child is already armed, parent death kills the direct child. Kernel exit closes its handles before an adopted zombie is reaped; the no concurrent execution claim is bounded by child death rather than exclusion until external orphan reaping.

Separate controlled-process tests verify replacement refusal, same-claim retry, independent jobs, retained permits during blocked heartbeat shutdown, inode replacement after reopening, copied-root boundaries and killed-worker recovery with unknown spent reservations. They do not establish numerical or physical correctness. This boundary requires the admitted worker implementation and a cooperating local filesystem; mixed older worker implementations, escaped descendants, distributed storage and unrestricted operator changes remain outside the qualification.

## Saved nodal reports and Workbench review

An authenticated `GET /v1/jobs/{job_id}/rc-corotational-report` derives deterministic JSON from a successful v6/v7 job's saved originals. The caller must supply `X-Structural-Expected-Request-Hash`, `X-Structural-Expected-Result-Hash` and `X-Structural-Expected-Evidence-Hash`. The service checks the stored event chain, counters, checkpoint, invocation outcomes, result and worker completion evidence in one SQLite read snapshot. A stale reference is rejected. Report reads create no job revision, numerical invocation, current source fingerprint or budget reservation.

Original request/checkpoint HTTP reads enforce the target's stored byte limit before a job view reads the request blob for its progress profile. After reading the original bytes, the route checks the current reference's length and digest before attaching its media type and hash headers. A concurrent reference change is rejected rather than labeling bytes from another checkpoint.

The export retains global UX/UY/RZ values in m/m/rad, FX/FY/MZ values in kN/kN/kN*m, signed load factors, fixed and reference load declarations and accepted checkpoint history. Authored targets, accepted response states, control attempts and reserved API invocations remain separate counts. Missing outcomes and unavailable work remain unknown. Free degrees of freedom have zero support reaction; their applied force is read from the external-load table. Member/material engineering and quantity/price tables are outside this report's scope.

`report_hash` binds the canonical body excluding that field. `X-Structural-Report-SHA256` binds the exact final bytes, and `X-Structural-Report-ID` is `rcc_` followed by that raw digest. The two hashes serve different purposes. The export has an independent 64 MiB cap. Workbench authenticates the request and report, validates declarations and custody fields in a dedicated worker, and displays one accepted nodal state at a time. Download preserves exact bytes. File reopening accepts only the exact report already authenticated for that session; a recalculated self-hash is insufficient. Account scope changes or disposal invalidate the review.

The actual tiny example fixture exercises separate worker execution, termination between chunks, older-backup activation, a fresh completing worker and repeated report reopening for v6/v7. It retains an unknown reservation and spends no new numerical work on report reads. Browser tests replay those saved bytes through controlled HTTP routes. These are software workflow observations, not a measured specimen comparison, deployed-service qualification, independent execution authentication, design approval or release readiness. The report retains the original experimental corotational authority flags and grants no new structural authority.

### Saved member, section and fiber details

`GET /v1/jobs/{job_id}/rc-corotational-detail-report` uses the same authentication,
three expected-original hash headers and read snapshot. Its separate
`durable-rc-corotational-detail-report.v1` document binds the nodal report and the
stored member, integration-point and material states to each accepted checkpoint.
The original nodal report and its `rcc_` identity remain unchanged. Detail report
IDs use `rcd_` plus the exact byte digest and have an independent 64 MiB limit.
An unavailable or oversized detail report leaves nodal review available;
authorization loss invalidates the whole review.

Workbench loads details only when requested and keeps the complete document in
its reviewer worker. It projects one selected member, section or fiber and bounded
history pages. All preload and subdivision states retain their saved order.
Global endpoint forces use kN and kN*m. Current-local forces are an explicit
rotation of those stored global endpoint forces along the current i-to-j chord;
they are not a continuous member-force diagram. Section curvature uses 1/m and
fiber stress uses MPa. Steel indices describe stored aggregate layers, not
individual physical bars. The detail export preserves exact bytes and the
original authority flags. Reading it does not invoke analysis, numerical recovery,
checkpoint replay or a new budget reservation.
