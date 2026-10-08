# Optional RC numerical phase execution policy

Date: 2026-09-30. Scope: the durable `bounded_rc_fiber_direct_control` worker.

An authored policy runs each analysis and its mandatory fresh verification in separate new Linux processes. It adds a phase deadline and observed direct-child cleanup to the existing fixed-chunk, solver-authoritative path. Omitting the policy preserves the existing in-process execution and request/resume identity; no default policy is inserted. The policy does not expand accepted structural models, change solver tolerances, or skip fresh verification.

## Request contract

This is an `execution_config` excerpt, not a complete job request:

```json
{
  "execution_config": {
    "chunk_target_count": 1,
    "maximum_api_invocations": 16,
    "phase_execution_policy": {
      "schema_version": "bounded-rc-fiber-phase-execution-policy.v1",
      "analysis_timeout_ms": 30000,
      "verification_timeout_ms": 30000,
      "termination_grace_ms": 100
    }
  }
}
```

The nested policy has exactly those four keys. Each duration must be an integer JSON token: booleans, floats, strings, missing keys, unknown keys and unsupported versions are rejected. Inclusive ranges are 1–3,600,000 ms for each phase timeout and 1–5,000 ms for termination grace. The example values are configuration examples, not a response-time promise.

`RCFiberPhasePolicy` is frozen. The policy remains part of the original canonical immutable request and resume-contract hash. Adding, removing or changing it changes that identity; an existing checkpoint cannot be resumed under a substituted policy. There is no worker-only policy override. The child receives the exact original request, fixed completed-target range and original restart bytes. Verification also receives the exact analysis result and native checkpoint. Reconstruction preserves constant loads, absolute targets, reversals, preload/genesis semantics, support flags and the authored assembly-reuse choice.

## Worker and process ownership

The optional path requires Linux, default `SIGCHLD` handling and exclusive ownership of waits for its direct children. The worker checks Linux and Python-visible `SIGCHLD` before reserving an invocation; the supervisor checks again before launch. Other reaper threads or native `SA_NOCLDWAIT` behavior are outside this runtime contract. A Python handler check does not attest their absence.

The worker owns authentication, leases, invocation reservations and durable publication. A fresh `sys.executable -I` process runs a stdlib bootstrap without a `preexec_fn`. Before importing the solver or package, it arms Linux `PR_SET_PDEATHSIG(SIGKILL)` and rechecks the expected parent PID. This closes the parent-death-before-arming race. Protection applies to the direct child and the Linux creating-thread relationship; it is not containment of arbitrary descendants.

Each child starts a new session. Cleanup sends TERM, then KILL when needed, to ordinary processes in that group. The parent observes direct-child exit with `waitid(..., WNOWAIT)`, keeps the PID owned while signaling, and requires an exact `os.waitpid` PID/status receipt before marking the child reaped. It does not treat `Popen.wait`'s synthesized exit-zero behavior after `ECHILD` as evidence. Lost wait ownership or unconfirmed signaling/reaping is an explicit cleanup failure. No subsequent numeric process-group signal is sent after ownership is lost. Escaped or reparented descendants are not covered by a cgroup or guardian guarantee.

Only fixed `PATH` and validated numeric thread-count variables are inherited. Credentials, loader-injection variables and arbitrary `PYTHONPATH` are not passed. Known numerical/schema dependency roots are supplied explicitly after death protection is armed. This is a local runtime consistency measure, not an untrusted-code sandbox or dependency qualification.

## Transport, identity and accounting

Binary segments preserve existing logical byte support without base64 transport duplication:

| Item | Maximum |
| --- | ---: |
| Original request | 16 MiB |
| API result | 512 MiB |
| Native checkpoint or restart | 8 MiB each |
| Verification or typed artifact-error report | 576 MiB |
| Sum of frame segments | 576 MiB |
| Metadata / retained stderr tail | 64 KiB each |

A frame also has a 52-byte fixed header. Role, length and aggregate limits are checked before accepting a frame. Nonblocking stdin/stdout/stderr are drained incrementally before waiting; excess stderr is drained but only a bounded tail is retained. All three owned pipe objects are tracked before setup can fail. Logical caps do not limit RSS, JSON copies, imports, durable-storage expansion or disk consumption.

The envelope binds phase, original and chunk request hashes, completed range, original restart, input result/native checkpoint and output segment hashes. Six local source hashes cover supervisor, bootstrap, API, request decoder, durable contract and policy. They detect inconsistent local inputs/replies; they are self-reported source identity, not independent producer, executable, transitive dependency, device or hardware attestation. Caller-supplied `source_revision` remains explicitly non-attesting. No object or exception pickle crosses the pipe.

A complete returned reply contains exact child integer `wall_ns` and `process_cpu_ns` for the API call plus artifact/report export. Imports, reconstruction and IPC are outside that measured child API scope. A complete raised reply can record the measured exception type and, for `BoundedRCFiberDirectControlArtifactError`, the validated original structured report. The worker reconstructs and validates the actual raw/native API result or required verification report before recording a complete outcome.

Timeout, crash, EOF, malformed/truncated/oversized transport, impossible timing, source mismatch, late reply or unconfirmed cleanup does not produce a measured invocation outcome. Its already reserved ordinal remains pending with unavailable work unknown; it is not refunded or recorded as CPU zero. Phase-specific errors use `rc_fiber_worker_{analysis|verification}_{timeout|transport_invalid|cleanup_failed|unsupported}`. Pre-reservation platform/reaping refusals have separate worker codes.

An analysis cutoff launches no verification. A verification cutoff retains any recorded analysis and the preceding verified checkpoint; it does not publish the unverified suffix. Observed lease-keeper failure triggers child cleanup and preserves the authority error. A stale worker cannot use that failure to overwrite a successor. Existing cancellation remains between chunks; this policy does not introduce tenant cancellation of a running numerical chunk.

## Deadline and cost limits

Each deadline starts before phase input preparation and covers preparation, launch, import, reconstruction, API/export, IPC and observed cleanup. Complete late replies and late child exit are rejected. Parent supervisor wall time includes child wall time; these nested measurements must not be added together. Durable invocation timing remains child API/export timing, not parent CPU or whole-worker time.

This is not a hard whole-job wall limit. `Popen` creation and uninterruptible kernel operations may exceed the configured duration. TERM and KILL cleanup can each consume a grace interval, plus scheduling and syscall overhead; an extremely short grace can yield explicit cleanup failure. Worker storage/bookkeeping, cumulative retries and lease-keeper shutdown are outside the phase deadline. The keeper's thread join has no separate bound. Polling checks observed keeper failure, not instantaneous lease takeover: heartbeat cadence and service calls can delay detection.

## Local verification and remaining scope

Run from the repository root with a compatible Python runtime. These commands exercise the named files; they are not deployment commands:

```bash
PYTHONPATH=src /usr/bin/python3 -m pytest tests/test_rc_fiber_job_contract.py -q -p no:cacheprovider
PYTHONPATH=src /usr/bin/python3 -m pytest tests/test_rc_fiber_phase_supervisor.py -q -p no:cacheprovider
PYTHONPATH=src /usr/bin/python3 -m pytest tests/test_rc_fiber_phase_worker_lifecycle.py -q -p no:cacheprovider
PYTHONPATH=src /usr/bin/python3 -m pytest tests/test_rc_fiber_phase_worker_native.py -vv -s -p no:cacheprovider
```

Retain original logs, JUnit, source hashes and pytest output stores. Use a new output directory for every receipt-producing run; do not reuse a retained `--basetemp` directory. Historical successes and the retained pre-fix reaping counterexample remain associated with their original source bytes. Do not aggregate earlier-source results into a final-commit qualification claim.

The source-specific supervisor tests use real processes for blocking and TERM-ignoring children, large pipes, invalid frames, lease failure, parent SIGKILL before/after arming, competing reapers and setup cleanup. Worker lifecycle tests exercise real reservation, unknown cutoff work, checkpoint preservation and authority boundaries. Synthetic transport entry points are private test seams, not a public production bypass.

The native regression file compares contemporaneous absent-policy full paths, isolated full paths and reopened fixed chunks for `proportional-v1`, `constant-v2`, `pin-roller-v4` and `loaded-zero-first-v4`. It checks original native state, response/member/section/fiber histories, preload plus zero-first-target semantics, exact child timing receipts and actual fresh verification. A loaded suffix that encounters a real solver line-search/nonconvergence failure retains its verified prefix and reports incomplete physical execution. An earlier successful native run used the `f9bef455` source snapshot: supervisor `3f161d38…`, bootstrap `1575a2b4…` and worker `e6ed0fe4…`. Its temporary originals subsequently became unavailable; the observed success does not replace a retained receipt or validate the later error-handling fixes. New checks retain their exact commit, source hashes, original logs, JUnit and output stores in the named permanent proof directory. Historical results are not counted as execution at a newer commit. No release commit or hosted-CI verdict is asserted here.

These are local software regressions on small authored models. Independent physical validation, external solver/experimental qualification, licensing and owner authority, actual deployment hardware, AI learning benefit, whole-worker RSS/disk quotas, cumulative cost and commercial readiness remain open. This change does not promote protected readiness ledgers or rerun a completed research campaign.
