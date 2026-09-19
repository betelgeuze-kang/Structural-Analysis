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
