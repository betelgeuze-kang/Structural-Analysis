# Exact-ID supplemental consumption in the production workflow

Implementation commit `388372c56d993afa72a73fa6b26e6c7fd17461d5` connects the
existing exact-ID consumer to Product State Current's supplemental download
step. The workflow uses the selected artifact ID, verifies the listed and direct
identity and downloaded ZIP bytes, and then performs its existing attestation,
runtime-seal and receipt checks. It no longer downloads that supplemental input
by name. This is a local integration candidate; no hosted Product State execution
or repair is established by the offline tests.

## Scope and source

The candidate is isolated on `codex/r2-production-consumer-20260908` at
`/home/betelgeuze/.codex/worktrees/r2-integration-20260908/건축구조분석`.
Its base is draft PR #434, exact head
`9ae22bfef8235f1d0594165898048f885e9e5417`, stacked on PR #432 at
`a892ca6b654880039656785ee621a68c11082496`. The AI roadmap worktree remains
separate; neither existing PR branch was changed or merged.

A read-only GitHub check still returned main
`4de4e3f55aae1d267cf704cec7d7533f3a627498`. Main has six commits absent from the
PR #434 base; that base has two commits absent from main. The production workflow,
strict JSON helper and existing repository workflow-contract test have identical
bytes between those two heads. This does not establish whole-branch integration
or eliminate the need to review and verify the eventual integration base.

## Preserved acceptance boundaries

The existing run-index lookup retains 30 attempts and ten-second retry delays;
run-metadata and artifact-list lookups retain three attempts and five-second
delays. A completed successful run must still match the exact source, `main`,
workflow family and allowed event. These are attempt bounds; the outer `gh api`
commands have no new per-command timeout. The consumer's direct metadata/ZIP
transport retains its existing byte limits and 60-second command bounds.

After lookup, `consume_supplemental_artifact.py` reads the saved run and inventory,
validates exact source/run/attempt/family/repository bindings, requires one
matching artifact, rechecks direct metadata and downloads only that ID. ZIP
size/digest and safe extraction remain the consumer's existing implementation.
Only the family parent directory is created beforehand. A pre-existing artifact
target is rejected, preserving the fresh-directory contract.

Only exit-zero `available` proceeds. Missing or expired evidence retains the
existing unavailable reason and removes the supplemental receipt. A consumer
failure or unknown stdout fails the step; ambiguity, changed identity or corrupt
bytes cannot be relabeled as unavailable. No duplicate is chosen by order or age.

The five family rows, their receipt paths and the complete block from
`technical_receipt` through final receipt `--check` are byte-identical to the
prior implementation. Each family still requires its receipt, handoff and
Sigstore bundle, then `gh attestation verify` with the common signer workflow,
exact signer/source digest, `refs/heads/main` and denied self-hosted runners.
All five seals must exist and report `technical_authority_eligible is True`
before receipt construction and validation. Existing runtime-seal failure stays
non-promoting; attestation or receipt build/check failure propagates.

Transport diagnostics are written exclusively to a fresh directory under
`RUNNER_TEMP`. Its path is exposed as a step output. An `always()` upload step
retains only that directory's JSON files in a separate artifact, named with the
workflow run and attempt, for seven days. The existing per-file size bound and
authority-false fields remain. No diagnostic enters a signed candidate or the
supplemental evidence input tree. Hosted retention itself has not been executed
or observed by this local work.

## Executed verification

The read-only identity CI workflow now includes the production workflow and
integration-test paths in both PR and main filters, and runs the new test file
alongside the existing producer and consumer tests.

- Existing producer identity unittest: 19 methods passed in 0.269 seconds.
- Existing consumer unittest: 28 methods passed in 0.040 seconds.
- Production shell integration unittest: 10 methods passed in 14.221 seconds,
  with additional scenarios inside those methods.
- Repository workflow contracts: 13 pytest tests passed in 0.33 seconds.
- Changed test files passed Ruff, formatting and diff checks. Both edited YAML
  files parsed with their workflow mappings intact. Actionlint and ShellCheck
  were unavailable and are not claimed as executed.

The integration harness extracts and executes the literal production `run`
block in a temporary directory. It copies and invokes the actual consumer,
identity verifier and strict JSON helper. Only GitHub transport/attestation,
sleep and the downstream receipt builder are controlled shims. Success checks
the exact sequence of five run/list/direct-ID/ZIP/attestation chains followed by
build and check. Negative cases cover missing and expired artifacts, duplicated
inventory, substituted identity/source, strict JSON rejection, corrupt ZIPs,
retry recovery/exhaustion, signature/build/check failures, blocked or missing
seals, and repeated execution with an existing extraction target.

These tests establish local transport and orchestration behavior. Their
synthetic signature replies and receipt files are not cryptographic, physical,
independent-verification or release evidence. They perform no structural solve,
live GitHub artifact mutation or production workflow execution. They do not
replace the unchanged real attestation and receipt implementations.

## Source-quarry inventory reconciliation

After the implementation commit, the existing deterministic builder rebuilt the
canonical inventory from its stored historical PR 77/78 metadata and the actual
candidate HEAD. Validation passed before the replacement was written. This used
the existing offline helper path; it did not fetch fresh GitHub data or use the
CLI's network-backed `--write` mode.

The structural diff contains exactly two values: PR 78's
`scripts/check_github_actions_runner_policy.py` current blob changes from
`01020a65305458d706c65d4e3090fb1c14701a9b` to the actual
`df11ab8214d89f7343131313a0dfaeecf3d0707e`, and the derived `inventory_digest`
changes. All 480 rows, 71 present/409 superseded counts, historical API metadata,
policy projection and authority boundaries remain unchanged. The inventory tests
pass all nine cases in 20.51 seconds. This repairs the diagnosed local inventory
drift; it does not repair main's separate live issue-state projection.

The before/rebuilt inventory, structural diff, validation reports and test log
are retained at `/tmp/structural-r2-source-quarry-rebuild-zndyzwk8/`.
The rebuilt inventory's file SHA-256 is
`9b045658c483dc653373f2ad2c63fc5ac0d148e855cc0fc3ec262b8d9011d0d4`;
`audit.json` has SHA-256
`7a3ff3f86bfc312068fdb2f07d79648f0a8ff5db18ccb3523c8527bae4e9d2af`.

## Local record and remaining work

`/tmp/structural-r2-production-observation.i4tuivcf/` retains the four test logs,
the implementation patch, the protocol and 11 exact source files. The source
copies were checked against Git at the implementation commit. Temporary test
scenario directories were cleaned by unittest; the record does not claim to
retain their individual ZIPs or command traces.

The separate PRs remain open. Their earlier metadata failures used old event
bodies; their current bodies contain the intended closing references, but a
fresh event-bound hosted check remains necessary. Their historical source-quarry
inventory drift is separate from main's live issue-state projection failure.
The final integration source must pass its inventory and repository checks.

Push, publication, merge, exact-head hosted integration, real diagnostic upload
and Product State execution remain unperformed. The cause of historical duplicate
artifact registration also remains unresolved. No external licensing, operator,
hardware, independent acceptance or release requirement is closed by this slice.
