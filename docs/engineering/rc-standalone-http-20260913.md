# Standalone strategy artifact delivery

Source `34a7ac63aa681cfbe53bbab53353d0700e69dc58` extends the existing immutable,
authenticated RC search HTTP mount to explicit standalone strategy v1 reports.
The original v2/v3 two-arm graphs retain their existing behavior.

A standalone report must bind a standalone plan naming the same strategy,
exactly one plan/arm, no oracle, and that arm's declared shortlist. A price-only
graph requires explicit null policy/training identities, no predictions or
ranking metadata, zero integer ranking time and no learned coverage audit.
It reads neither policy nor historical training files. A learned graph retains
the existing policy/training hash bindings. Rehashing conflicting metadata does
not make a mixed graph admissible.

The host pins the report hash before publication. Existing bounded reads,
artifact byte references, exact path allowlists, immutable snapshots, tenant
authorization and read-only routes remain active. Other arms and unreferenced
files are not served. In particular, the numerical CLI's volatile
`strategy-runtime.json` is not bound by the search report and is not silently
added to this graph. A future cohort adapter must explicitly bind runtime
sidecars before displaying their timings.

This mount validates artifact identity/access, not physical correctness or
complete engineering semantics. The current Workbench validator still rejects
standalone schemas; this change does not enable their React presentation or
grant the standalone report a two-arm comparison identity. Browser-side
validation/display and repeated-cohort integration remain subsequent work.

## Verification

All 46 focused HTTP tests pass, including twelve new standalone cases. The new
tests use controlled metadata conversion of existing numerical fixture bytes;
they do not constitute new physical analyses. They verify single-strategy reads,
exact response bytes, unavailable other-arm/runtime routes, authentication and
rejection of rehashed mismatches (strategy, oracle, arm set, schema downgrade,
policy/training metadata, missing explicit nulls, boolean time and shortlist).
Ruff, scoped mypy and diff checks pass.

The eight actual directories from the prior frozen standalone CLI experiment
are additionally mounted through a local WSGI listener. Each admitted file is
first matched against that experiment's sealed inventory. All **568 successful
HTTP responses** match original bytes and lengths. **32 requests** for missing
authorization, another tenant, another strategy or the unbound runtime sidecar
are denied. Source files remain unchanged across the observation, and the
current Git source archive is retained. The listener and thread close normally.

The observed bundle-construction/HTTP/shutdown interval is 0.388491729 s on the
local shared host. It excludes source archiving, interpreter startup and later
receipt writing, and is not a network or deployed-browser benchmark. No solver,
fit or browser runs. Hosted CI completion, standalone Workbench acceptance,
independent validation and full roadmap closure are not claimed.

The [machine summary](rc-standalone-http-20260913.summary.json) binds current
delivery source, original numerical inventory, response counts and seal. The
new packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-standalone-http-1i7tu5jj`:
4 files / 51,778,618 bytes, all reread against its sibling inventory. Inventory
SHA-256: `b3c98540295441e13b343b5bf7f8f6d09f3b0af12cb88a5c3d46797ef9ae48d7`.
The original numerical packet is unchanged.
