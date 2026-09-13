# Workbench durable failure state and diagnostic publication boundary

The job panel previously omitted `error_code` even though the validated durable
job view supplied it. It now displays the last service failure code, including on
requeued attempts, and explains that saved progress excludes some attempted work.
No solver convergence, accepted result or failure-history authority is inferred
from this orchestration value. A job without an error explicitly says none was
reported and does not display the failure explanation.

The existing local HTTP browser fixture now creates a genuine service claim and
non-retriable failure transition before submitting its separate queued job.
The injected `synthetic_transport_failure` is transport test data, not a Newton
failure. No numerical worker runs. Four actual HTTP/browser tests passed in
24.5 seconds: original queued-request bytes and tenant isolation, credential
rejection, and failed-state display at 1280 px and 390 px widths. Both failed
views retain unavailable convergence and engineering ResultIR, with no RC or 3D
result review. The pinned Node v24.20.0 workflow also passed TypeScript, production
build and viewer delivery checks. Python fixture Ruff passed.

This does not connect the new public planar `observed_load_path` to Workbench.
The current nonlinear worker calls `fail_job` when the result validator blocks
publication. Job view v1 prohibits result/evidence artifacts on non-succeeded
jobs, and the browser intentionally honors that contract. Reusing the successful
result slot for failure diagnostics would violate it.

The remaining integration requires a distinct diagnostic artifact contract with
request, attempt and source-result bindings; atomic persistence with the failed
transition under the active lease; tenant-authorized original-byte retrieval;
and a browser projection that validates the diagnostic fields while retaining
unavailable numerical and engineering authority. Unknown execution or exception
work must stay unknown, not zero. Retry/cancellation/lease expiry must not attach
another attempt's diagnostic. Those persistence, authorization and stale-attempt
tests are prerequisites to claiming detailed failure-cost visibility in Workbench.
The current change closes only the missing service-failure display.

The later [durable diagnostic integration](durable-failure-diagnostics-20260913.md)
implements the local worker attachment, atomic storage and authorized original
retrieval. The [current-attempt diagnostic review](workbench-failure-diagnostic-review-20260913.md)
subsequently connects bounded browser validation, display and original downloads.
