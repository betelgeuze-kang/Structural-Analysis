# Portable process-cost cohort v2 — 2026-09-13

Source `bea69d0b7819c6646243f079f361e59dd05a92c0` extends `create_rc_strategy_cohort` with optional original
`process_observations` bytes. Omitting them produces the unchanged v1 schema;
including them produces `rc-control-strategy-cohort-artifact.v2`.

The v2 root adds an exact byte reference to `process-observations.json` and a
`process_cost_accounting` object. The process document contains exactly one
`processes` field. Loading validates the existing original design graph and CLI
costs first, reads the bound process bytes, and recomputes enclosing process
costs using the prior accounting API. It rejects mismatched bytes, costs, schema
fields, paths and duplicate JSON keys. Process records remain caller-bound clock
observations, not attested timings or independent physical evidence.

The original process bytes and all child design/runtime bytes are preserved in the
immutable snapshot. File export still creates a new directory and writes the root
manifest last. The existing authorized read-only HTTP application serves v2 through
the same validated bundle type. Existing v1 manifests and tests remain supported.

## Verification

82 focused tests passed: 23 cohort tests (including 8 additions), 13 process-cost
tests and 46 artifact HTTP tests. Ruff, focused mypy and diff checks passed. New
coverage includes exact process-byte export/reopen, metadata arithmetic changes,
boolean count aliases, path substitution, schema downgrade, missing fields and
duplicate process-document keys. These are controlled contracts, not performance
or physical qualification.

An original-data observation checked 576 study/runtime inputs against the sealed
standalone inventory and checked the prior process-cost receipt against inventory
`04fedf2caaf4ea494e4aef479dc955a278cf2464af4d6074f5efb6eaad4cde39`.
The process document is explicitly assembled from that earlier record's bound
observations; it is not presented as a new native process measurement.

Export/reopen produced 578 files / 21,651,704 bytes with cohort hash
`sha256:fe56efb76779f4a2b2b27bba4e7059434afafa9359621592dcf6c0f6a62aef75`. All 578 actual HTTP responses matched the snapshot
bytes; six unauthorized, wrong-tenant, method and unknown-path requests were denied.
The listener was closed. The complete observation interval was 544.914108 ms,
excluding source copying, final receipts and sealing; it is packaging/delivery
measurement and does not enter strategy runtime ratios.

The process accounting exactly matches the previous four-pair calculation:
price processes 30.506515408 s, learned processes 30.199308686 s and historical
training 2.761753795 s counted once. Two selections are incomparable, so the
aggregate ratio remains null. No fit, nonlinear solve, browser run or independent
physical verification was performed.

## Records and remaining work

Packet `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-process-strategy-cohort-9jcctkrl` contains 587 files / 21,831,531 bytes, bound by
sibling inventory SHA-256 `539c0acdbd9100b4a45e8a303c257e277c238d9bab2b89a4df388ae5098d6453`. It includes exported
originals, scoped source copies, the executable observation driver, process-input
provenance, HTTP receipts and summary. Earlier sealed packets remain unchanged.

Workbench currently supports cohort v1 only and rejects v2; this change does not
silently omit process costs in the browser. Independent browser recomputation,
process-record download and display are the next integration step. Complete matched
campaign costs, independent cases, hosted CI and physical qualification remain open,
as do the established licensing, owner/administrator and hardware dependencies.
