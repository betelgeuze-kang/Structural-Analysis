# Portable strategy cohorts with bound runtime records

Source `e55370683329cb401d2d3e8c7246906b9c26625c` adds
`RcStrategyCohortBundle` and `create_rc_strategy_cohort`. A cohort binds each
original standalone study graph and its original CLI runtime bytes under a
relative path. Its `cohort.json` identifies both strategies in every pair and
contains recomputed cost accounting. The existing authenticated immutable HTTP
mount now accepts this explicit bundle type as well as individual studies.

The builder accepts a tuple of pairs, each mapping `price_order` and
`learned_order` to `(RcSearchArtifactBundle, original_runtime_bytes)`. Original
model, result, checkpoint, verification, plan and training bytes are preserved.
Up to 64 pairs and the existing aggregate 1 GiB transport limit are supported.
The cohort source revision is a declaration, not an attestation.

```python
from pathlib import Path
from structural_analysis.execution.rc_strategy_cohort import create_rc_strategy_cohort

# pairs contains already loaded original study bundles and their runtime bytes.
cohort = create_rc_strategy_cohort(tuple(pairs), source_revision=source_revision)
cohort.write_directory(Path("new-cohort-directory"))
```

`RcStrategyCohortBundle.from_reader` requires the pinned cohort hash. It checks
strict ordinal/strategy paths, exact byte lengths and SHA-256 digests, original
standalone graph bindings, runtime/report identities and recomputed paired
costs. Rehashed cost changes, boolean counts, non-integer lengths, alternate
study identities and path substitutions reject. Original runtime digests bind
data; they do not attest measurement truth or independent provenance.

The directory exporter creates a new destination and writes `cohort.json` last.
It never overwrites an existing export. A failed earlier write leaves partial
files without a publishable root manifest; it does not delete those files.
This is not a crash-durability/fsync guarantee or cross-platform qualification.
Snapshots remain immutable after construction and HTTP clients cannot read
unregistered files, access another tenant, or mutate/execute the bundle.

## Original-data export and HTTP observation

All four pairs from the sealed standalone experiment are included, in the
original budget/order groups. All **576 original study/runtime files** match
that packet's existing inventory. Creation, export and reopening produce the
same **577-file / 21,645,732-byte** graph, including the new root manifest.
The reconstructed accounting retains four pairs, two incomparable pairs and
a null aggregate learned/price ratio. No numerical output is regenerated.

The reopened export is mounted through a local WSGI listener. All **577 HTTP
responses** match snapshot bytes and lengths. **Six requests** for absent
authorization, another tenant, mutation, an unknown file, price-only policy
metadata and an unregistered root runtime file are denied. The listener/thread
close normally. Source bytes match the committed implementation before and
after the observation.

The observed original-read/build/export/reopen/HTTP/shutdown interval is
0.539711567 s on the shared local host. It excludes source copying, receipt
writing and sealing. It is not a deployed-network or browser benchmark. The
observation runs zero solver calls, fits or browsers. Metadata/accounting and
byte checks do not independently replay physical artifacts or qualify models.

Ninety-three focused cohort, cost, HTTP and workflow tests pass, followed by one
additional byte-length type test (94 distinct local tests). The tests include
round-trip export, exact source bytes, immutable storage, duplicate-execution
rejection, runtime substitution, changed native bytes, byte budgets, rehashed
cost/type/path changes and interrupted export. Controlled metadata/runtime
fixtures are not performance evidence. Ruff, scoped mypy and diff checks pass.
The development workflow now selects 29 test modules; no hosted pass is inferred.

## Remaining connection

The original per-execution study files and bound cohort costs can now travel
together. The Workbench cohort validator and aggregate comparison screen still
need implementation; the existing single-study validator does not accept
`cohort.json`. Startup/transport/audit costs remain outside the CLI cost scope.
Independent validation, learned net benefit, broader held-out cases and full
roadmap closure remain open.

The [machine summary](rc-portable-strategy-cohort-20260913.summary.json) binds
source, graph identity, reconstructed costs and seal. The packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-portable-strategy-cohort-_6vq4tp3`:
584 files / 21,813,110 bytes, all reread against its sibling inventory. Inventory
SHA-256: `390442ef9599a5bcbe29d727ae0ec1dbb2b9633130968405c94c63d1f357c740`.
The prior sealed numerical and verification packets are unchanged.
