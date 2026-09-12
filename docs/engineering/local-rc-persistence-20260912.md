# Persistent verified RC originals, cooperative budgets, and runtime inventory

## Scope

This change is an extension of PR #442, base `4a856164a999aefb8204fd63eb8bbb150862d463`.
It changes no material model, solver tolerance, reference metric or engineering
acceptance rule. Existing scientific comparison still runs fresh paths. The local
execution default remains process-local; `--store-root` explicitly enables the
new persistent mode. This is not a production authentication service or GPU
solver qualification.

## Persistence

`RCResultRepository` adapts the **existing** `DurableJobService` tenant authorization,
SQLite transactions and immutable blob storage. It adds one versioned index table;
it does not replace the job schema or create an unrelated object store. The
adapter intentionally uses the existing private service methods and must be
regression-tested when those methods change.

Only an internally generated original that passed the existing virgin analysis
and fresh full replay can be admitted. The evaluation report must be published
before durable registration. The index commits after artifact writes. An I/O
failure rolls back the index, while immutable orphan blobs can remain. No
unreferenced file, external receipt, pickle or arbitrary file import creates a
cache entry. Digests provide integrity; they are not independent proof of physics.
The OS owner and local service host remain trusted.

Lookup binds the entire detached model/provenance, constant preload and target
history, solver settings, source label, package/schema bytes, Python/numeric
library identity and thread configuration. Native NumPy/SciPy library bytes are
included; the strict repeated hashing is **measured**, not optimized away. The
caller-supplied source label is not an attestation, and not every conceivable
process-global numerical setting or system shared library is attested.

Persistent mode requires POSIX, one host and a local filesystem. Do not place the
SQLite database on a multi-host network share. Per-key advisory locks prevent
concurrent duplicate evaluation and are released by the OS on process exit.
Timeout is an error, not permission to steal a live worker's lock. No SQL
transaction is held for the duration of the nonlinear solve.

The default catalog cap is 256 entries / 512 MiB of **referenced** snapshot bytes.
It is not a whole-disk or peak-RSS quota. Interrupted writes, lock files and SQLite
metadata are outside that total; no automatic garbage collection is supplied.
Snapshot capture is also bounded by the existing memory admission limit.
A full catalog refuses new admission without invalidating a completed physical
result. Disk corruption rejects rather than silently solving to hide it.
The first admitted original is retained when an explicit fresh replay runs.

The CLI pins its first tenant/token verifier in a local owner file; reopening with
a different token cannot silently reset authority. The raw token is read from
`STRUCTURAL_RC_STORE_TOKEN`, never from a command-line argument or a result.
Use a retained randomly generated secret of at least 16 bytes. There is no token
rotation/recovery UI; protect and back up local credentials. A partially written
owner file rejects and needs explicit local repair rather than being overwritten.

## Cost and time accounting

Reused originals report zero **new** numerical calls and retain historical work
separately. They never claim a fresh replay on this call. Evaluation stages expose
input checks, lock wait, source checks, lookup and evaluation/reuse cost. The
separate `completion.json` measures evaluation-report writing and durable
publication; it excludes only its own final write. Whole CLI launch timing is
still needed for process startup and final batch-report cost. Stage times are
observations, not correctness gates or a general speedup claim.

```sh
# Set STRUCTURAL_RC_STORE_TOKEN securely and retain the same value for this store.
PYTHONPATH=src python -m structural_analysis.benchmark.rc_control_local_search_cli \
  --model /path/model.json --request /path/request.json \
  --experiment /path/prices-and-limits.json \
  --source-revision <reviewed-40-character-commit> \
  --store-root /private/local-rc-store --tenant-id lab \
  --max-new-model-analyses 4 --max-wall-seconds 600 \
  --stop-file /private/stop-rc-search --output /new/output-directory
```

A later process can use `--max-new-model-analyses 0` to permit only existing
eligible originals. Price and supported limit changes rescreen/reprice those
originals. Changed physical inputs require new work. A stop file or elapsed
budget is checked **between models**, not inside Newton or during verification;
a single running model can exceed the requested wall budget. Cancellation keeps
completed originals, leaves unrequested outcomes unknown and does not invent a
pool minimum. Restart the same search in a new output directory to reuse the
completed models. This is restartable candidate orchestration, not a new partial
nonlinear-checkpoint resume implementation.

## AMD environment inventory

```sh
PYTHONPATH=src python -m structural_analysis.execution.local_runtime_doctor
```

The doctor reads bounded Linux DRM vendor/device identifiers, KFD accessibility
and executable locations. It runs no external program, kernel or GPU solver.
The report always leaves GPU parity/performance false and qualified GPU profiles
empty. A visible AMD card or installed compiler is not execution evidence.
No automatic backend switch or physics-setting change is added.

## Validation and remaining integration

Tests use the actual small 600 kN preload / three-reversing-target RC path as
well as explicitly labelled fault injection. They cover cold/reopened processes,
repricing/rescreening, exact original bytes, changed loads, tenant/scope rejection,
quota refusal, corruption, output/blob failures, OS lock release on process death,
actual process termination during index publication, same-key serialization,
cooperative budget/cancellation and synthetic device inventory. They do not
establish independent physical validity, power-loss durability on every filesystem,
GPU speedup, hard memory enforcement or production identity management.

The local environment is the base CI package plus changed files, not a complete
repository checkout. Required same-head remote CI remains necessary before merge.
Parallel worker-pool scheduling, GPU kernel integration/measurement, deployment,
web consumption of these new local reports, global disk quotas/GC and further
learned-policy research are **not** implemented by this slice.
