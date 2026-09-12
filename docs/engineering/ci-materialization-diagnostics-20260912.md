# Preserve failed full-suite materialization diagnostics

Full repository shards can fail in the evidence preparation step before actual
pytest execution. The latest inspected run retained only the separate development
JUnit artifact, so the gate names were visible in raw logs but the detailed
rewritten comparison receipts were lost with the runner.

The workflow now gives materialization a step id and, **only when that step fails**,
uploads four explicit files: a failure-context JSON, the code-to-code technical
receipt, the modal/buckling technical receipt, and the internal license diligence
manifest. Artifact names include shard and tested Git SHA; retention is seven days.
No broad directory, hidden-file, log or credential upload is introduced.

The receipts are already tracked files. If preparation stops early, some may still
contain checkout bytes or partial rewrites. The context therefore states that
these are diagnostic only, may include tracked or partially rewritten receipts,
and attest neither new generation nor qualification. It records workflow SHA,
run id, attempt and job. File absence is reported as a warning; it never changes
the original failing preparation outcome. Missing files are not successful checks.

`--fail-blocked`, the required external comparisons, normal full-test success
condition and final aggregate requirement remain intact. There is no
`continue-on-error`. The artifact upload exposes a failure; it does not qualify
an external reference or make the full suite pass.

Sixteen workflow tests pass, including failure-only gating, the exact file
allowlist, preserved aggregate behavior and actual execution/JSON decoding of
the context script. Ruff and diff checks pass. These checks do not prove hosted
upload availability; inspect a subsequent same-head failed shard's artifact
before making that claim. Validation and source copies are retained with the
[full-cycle numerical study](rc-full-cycle-native-reuse-20260912.md), after its
numerical execution and separate audit have completed.
