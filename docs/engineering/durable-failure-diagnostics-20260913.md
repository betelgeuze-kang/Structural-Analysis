# Durable attempt-specific nonlinear failure diagnostics

The nonlinear worker now attaches a diagnostic when an actual blocked
corotational result fails the core publication gate. The service reconstructs
the expected binding from its immutable v1 request, current attempt and attached
checkpoint. It independently checks the submitted model checksum and authored
profile, controls, tolerances, iteration limit and backend without running a
solver. Extra core-generated configuration fields remain observations, not
independently authenticated execution evidence.

Existing v1 requests have no source-revision field. Their diagnostic binding uses
null, explicitly unavailable, rather than assigning the current checkout or a
fabricated commit. The separate transport contract now permits that null label.
Original result bytes, canonical result hash, exact request identity and attempt
remain bound and verified. Unknown source provenance earns no external credit.

`fail_job` accepts an optional nonlinear failure result. Under the active worker
lease, it validates and content-addresses the diagnostic, inserts an immutable
`job_failure_diagnostics` row keyed by job and attempt, and appends the diagnostic
reference to the failure event in the same SQLite transaction. Its deferred
foreign key references that exact event revision. The optional path preserves
existing failure transitions without diagnostics, including other solver profiles.
An interrupted transaction can leave an unreferenced blob, but no diagnostic or
failure transition is published. This is the existing content-store orphan model,
not an assertion that no filesystem write occurred.

`GET /v1/jobs/{job_id}/failure-diagnostics/{attempt}` returns original diagnostic
bytes after tenant authorization, full job integrity verification, blob hash and
length verification, and reconstruction against the stored request and failed
attempt. The integrity audit checks record/event correspondence in both directions,
including deletion of a diagnostic row. Historical attempts survive retries and
cannot be overwritten with an expired or previous lease. Missing diagnostics
return 404, absent credentials 401, and another tenant receives 404. Reads accept
no body. The route uses the existing bounded ordinal syntax (1 through 9999).

Job view v1 remains unchanged: failed jobs expose neither result nor completion
evidence. The diagnostic route grants no numerical, design, release or external
validation authority. It does not assert total API work, and it cannot recover
work from an exception that produced no result. Worker HTTP mutation payloads
are unchanged; attachment is currently through the local nonlinear worker/service
call, not a new remote worker upload interface.

Tests execute a real failed Newton path, reopen the service, compare HTTP bytes,
retry under optimistic request/checkpoint bindings and verify both attempt files.
They also cover tenant isolation, stale/expired leases, injected transaction
interruption, removed records, and rejection of another model/config/profile.
Both neutral-model and ModelIR worker failures were exercised. The diagnostic,
public failure contract and durable job modules passed 70 tests in 19.07 s.
Existing RC and Frame3D job-service modules passed 122 tests in 49.44 s. Four
existing real HTTP/browser tests passed in 24.6 s after the shared service/route
changes; these verify the service-failure-code view, not detailed diagnostic
display. The pinned frontend TypeScript/build/delivery checks and Python Ruff
passed.

The previous published source `6d28f52e0` separately completed development CI with
951 tests in 1087.58 s and Native PR Fast success. Its full Python shards failed
external evidence preparation: the inspected shard retained `legal_approval=False`,
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`;
these preceding-head CI results do not qualify this implementation. The full
roadmap and independent verification requirements remain open.

Remaining Workbench integration: fetch the explicit failed attempt, verify its
original bytes and request/attempt binding in the browser, validate observed-path
counts, and display partial work with unavailable numerical authority. The current
panel displays the service failure code only. Detailed failure-cost visibility
must not be claimed complete until that path is exercised end to end.
