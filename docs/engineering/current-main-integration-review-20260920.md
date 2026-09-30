# Current-main supplemental integration review

Reviewed development `02c6ed78ef12e3989cbdd3eed7c2fc37dcad08bd` against current main `234c3122c78dea064411aa16b06b18ab16157576`, independently read from the GitHub branch endpoint. Local main tracking agrees. The graph has 573 development-only and four main-only commits; this does not mean four missing implementations.

Of the 15 files changed by those main commits, **13 have identical Git blob IDs** in development: all four relevant workflows, both identity/consumer scripts, the runner policy, three historical records and three identity/consumer/production tests. Two files differ:

- `tests/test_repository_python_workflow_contract.py` retains additional development-contract and failed-materialization tests. A three-way `git merge-file -p` against the common base exits zero and produces exactly the existing development bytes. SHA-256: `ebf29e5a5ff9ae1997a499001e3e1ac51b236403f0cc0d226b86069e8d148430`.
- `canonical/source-quarry-inventory.v1.json` has the single textual conflict block in its generated `inventory_digest`. The offline validator rebuilds the current inventory successfully: **480 entries, 71 present, 409 superseded, zero blockers**. Its historical API snapshot is not freshly authenticated (`github_api_verified=false`).

The installed Git uses the older three-argument `merge-tree` interface. Its read-only preview used the exact common base and both reviewed commits. No checkout, index, branch ref or existing worktree was changed. The unsupported `--write-tree` invocation failed before producing a preview; the successful three-argument preview is the evidence used here.

The original production transport/identity/consumer and repository workflow tests were rerun: **75 passed, 137 subtests passed in 15.23 seconds**. They use controlled transport/signature responses and establish software contracts. They do not execute real external attestation, provide independent physics, or qualify a merged tree.

## Remaining integration work

An eventual authorized merge must regenerate the inventory against its actual resulting source and repeat applicable combined-source checks. The present inventory validation is evidence for the present development tree; copying an older digest or treating this preview as an actual merge is insufficient. All external replay, license, operator, hardware and signature requirements remain in force.

This review confirms that missing supplemental transport code is no longer the integration blocker. Branch ancestry, generated metadata on the combined source and authoritative execution remain open. [Exact component identities and validation summary](current-main-integration-review-20260920.summary.json).
