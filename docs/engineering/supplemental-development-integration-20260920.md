# Current-main supplemental transport integrated into development

The development branch did not contain current-main PR #440's supplemental
artifact verifier/consumer or workflow wiring. This change applies the reviewed
file changes from main `234c3122c78dea064411aa16b06b18ab16157576` to the development
checkout, preserving its later RC code and development CI selection. It does not
merge either branch or assert PR mergeability.

Imported components:

- Exact run/attempt/source/family and unique artifact-ID verifier, streaming ZIP
  digest/length checks and bounded diagnostics.
- Consumer that rechecks saved API identities, downloads by verified ID, validates
  archive content and extracts to a fresh private directory. Missing/expired
  evidence stays unavailable; ambiguous/corrupt evidence fails.
- Post-upload identity job outside the OIDC signing job, with read-only workflow
  permissions, and exact-ID consumption in Product State Current before the
  existing Sigstore and receipt checks.
- Dedicated contract CI, production-shell mock regressions and hosted-runner
  allowlist entries. Existing scientific and independent acceptance gates remain.

The implementation scripts and new workflow/test files are imported from exact
main blobs. Existing workflow and contract-test edits use the main patch against
the current branch rather than replacing whole files. Source-quarry metadata is
rebuilt from its preserved historical API snapshot after committing the actual
source files; historical PR identities and owner scope dispositions must remain
unchanged. Main's entire older inventory is not copied over the newer branch.

Local identity/consumer/production workflow/repository workflow checks passed:
75 tests and 137 subtests in 15.38 s. These use controlled service responses and
execute the production shell boundary without contacting external artifact or
signing services. They do not establish successful real supplemental attestation
or independent physics. Ruff, diff checks and the live workflow runner policy
check passed (49 workflows / 90 runner declarations).

Actual source-bound producer execution, artifact/signature availability, current
combined CI and an authorized main merge remain separate requirements. This
integration closes missing local production transport plumbing, not those gates.

The post-source-commit offline inventory rebuild updates six `current_blob_sha`
values and the inventory digest only. All original PR/file identities, owner
scope fields, statuses and disposition reasons are unchanged. Inventory and runner
policy regressions then passed **24 tests in 20.73 s**, resolving the four stale
inventory failures seen before rebuilding. This was an offline snapshot rebuild,
not a fresh assertion that historical GitHub metadata has been re-fetched.

## Current-main merge preview and historical records

A read-only `git merge-tree` preview used base
`4de4e3f55aae1d267cf704cec7d7533f3a627498`, development head
`19f85db45ad18f2b29aa59fedf2dd2066d506ef6` and independently rechecked main
`234c3122c78dea064411aa16b06b18ab16157576`. It found one textual conflict block,
in `canonical/source-quarry-inventory.v1.json`. The workflow contract test merges
without a conflict; the previously imported executable transport and workflow
changes introduce no further textual conflict in this preview. This is a local
merge preview, not an actual merge, GitHub mergeability guarantee or combined
post-merge validation.

The main/development inventory difference is precisely 14 `current_blob_sha`
values and `inventory_digest`. All other metadata, dispositions and historical
PR identities agree. The development inventory currently passes its offline
480-file validation (71 present, 409 superseded), without claiming a fresh GitHub
metadata verification. An eventual authorized merge must regenerate and validate
current hashes against the resulting source tree; choosing main's stale hashes
or dropping the conflict markers without rebuilding is not a valid resolution.
No inventory field or acceptance rule was changed in this preflight.

Three previously absent historical records were copied byte-for-byte from that
exact main commit: `supplemental-current-main-20260909.md`, its JSON summary, and
`supplemental-production-consumer-20260908.md`. Their original dates, revisions,
limited test scopes and pending attestation statements remain intact. They are
historical integration records, not new signed acceptance or current execution
receipts. No branch ref was merged, no workflow dispatched and no release made
as part of this preview/document import.
