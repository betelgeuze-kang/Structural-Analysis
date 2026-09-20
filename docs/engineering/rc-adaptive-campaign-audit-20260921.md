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
