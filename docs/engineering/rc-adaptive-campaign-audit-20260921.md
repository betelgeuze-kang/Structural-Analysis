# Reusable read-only audit of adaptive recovery campaigns

`scripts/audit_rc_adaptive_continuation_campaign.py` audits an original campaign
directory produced by the matching repository runner. It does not rerun numerical
solves or fit a policy. Run from the intended source checkout with `PYTHONPATH=.:src`:

```text
python3 -m scripts.audit_rc_adaptive_continuation_campaign CAMPAIGN_DIRECTORY --output AUDIT_FILE
```

The output must be outside the original campaign and is opened exclusively; an
existing file is never overwritten. Metadata uses strict duplicate-rejecting JSON
and byte budgets. Missing/unknown observations are rejected, while known failed
native paths remain visible and never become completed histories.

The audit checks the declared canonical cases, requests, arm ordering, recovery
profiles, binary64 arithmetic and fixed comparison tolerances. It validates
report/path/native hashes and phase bindings, reconstructs the outer accepted
checkpoint chain and response-to-native-step bindings, checks original target
ordering and history length, and compares ordinary as well as internal trial work
against native result counters. Every recovery trial retains the outer material
parent; absolute seed handoff and the adaptive fraction schedule are checked.
Native-call budgets, Newton iterations and linear solves are all accounted for.

Fresh-reference comparison gates are recomputed from original response histories.
A ratio requires both modes to complete, match full histories and pass fresh
comparisons in both repetitions, with exact repeated complete histories/checkpoints.
A partial path cannot qualify by being relabelled complete. Valid positive timing
fields are required, but the tool does not independently authenticate measured
clocks or the caller's source-revision attestation.

The result explicitly retains `numerical_reexecution_performed=false`,
`original_execution_clocks_authenticated=false`,
`independent_physical_validation=false`, and `policy_promoted=false`.
Internal consistency and hash binding are not independent execution provenance
or physical qualification; coherently replaced records require a separate trusted
execution/replay mechanism, not this read-only audit alone.

## Regression checks

Forty tests pass across audit, runner, repository workflow and strict-YAML checks.
The audit fixture executes a real short/40 mm campaign with fixed failure and
adaptive completion. Audit leaves its original JSON bytes unchanged and reports
16 paths with two complete, retaining a null ratio. Negative tests reject rehashed
false completion, rehashed additional/ordinary work, missing comparisons,
duplicate metadata keys, invalid timing types/values, escaping trial references
and output inside original evidence. A partial history cannot be marked complete.

The two campaign modules are in the independent development-contract CI job.
The full repository gate still requires all full-suite shards; adding these
checks does not bypass external evidence preparation or other release conditions.

## Actual original-campaign readback

Committed auditor `1ccffdcf0985bf97275f5531c1b3b961fbfedcb2` was run against the
retained 128-path campaign from source `84714992a`. Its case outcomes and all
previously reported totals match the separate original audit exactly: 70 complete
paths, 802 native calls and 4,702 Newton iterations. It additionally reconciles
4,702 linear solves directly against native records. No numerical reexecution
was performed and no original campaign file was written.

The separate output packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-public-adaptive-audit-q_o6bshv`.
It retains the audit output, CLI output, auditor bytes and source metadata.
All four inventory entries were reread and hash/length checked; inventory SHA-256:
`f137f494e0f0428db0c1f1a4ebb25b38bf250ebe53ba153b852db9eb7521d836`.
This confirms reproducible consistency checks, not the authenticity of original
execution clocks or independent structural accuracy. Complete user-flow audit/UI
costs remain a separate measurement requirement.

## Optional per-invocation audit cost

Add `--timing-output /separate/directory/cost.json` to record wall and process CPU
nanoseconds from entry to the audit call through closing the serialized audit
output. The timing receipt binds to `audit_hash`; nondeterministic clock values do
not enter the original audit result or its hash. Both outputs must be distinct,
outside original evidence and not already exist. Files are created exclusively.

This optional receipt measures only a successfully returned audit and its output
write. It excludes interpreter startup/imports, argument preflight, its own write,
stdout, numerical solves, transport and browser review. It is not a replacement
for enclosing-process measurements or complete user-flow costs. Failed audits do
not emit a success timing receipt; their costs still require an enclosing runner.
If writing the timing file fails, a previously written valid audit may remain and
the CLI fails; no rollback deletes that evidence. Cache state is uncontrolled.

Twenty-three audit/runner tests pass after this addition, including exact separate
clock attribution, unchanged result payloads, and fail-fast rejection of colliding,
existing or original-directory output destinations. Ruff and whitespace checks pass.

Actual frozen-source check at `9f36e540d799febbbb117c78e539a7075ed12afe` audits the original 128-path campaign with an exactly unchanged audit object/hash. The separate scoped receipt records 10.214824533 s wall and 10.213985152 s process CPU. This single observation excludes startup and the other receipt-listed stages; it is not directly comparable to the earlier enclosing-process timings as a speedup. Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-scoped-audit-cost-lp65up0a`; inventory SHA-256 `94afc3efdbc140fad265f335d033a5c473cb0aea508bd364fe9c7d8b7c9e6beb`. All entries were reread and verified.
