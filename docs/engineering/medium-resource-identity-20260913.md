# Resource identity on blocked medium-scale receipts

Diagnosis started from the full-suite failures recorded at
`df60b7d3913f8fe095788f07ace95302d02f6cd3`. A fresh isolated
`generated_braced_truss_tower` execution on parent source
`166f6a14da8fb28481c14d7e87d2f009429e3fb7` passed all numerical and resource
gates (1.657 seconds inside the execution interval; 122,138,624 bytes peak RSS).
This one observation does not explain the earlier long-suite resource failures
or establish independent physical verification.

A separate receipt-validation defect was reproduced. If peak RSS already exceeded
the 1 GiB policy limit, substituting the other platform's measurement method left
the derived memory gate false. The validator accepted the contradictory metadata
because the stored gate was also false. The regression first produced one pass
and one failure: the ordinary receipt rejected the substitution, but the
over-limit receipt did not.

Resource identity is now checked independently of the numeric gate. Measurement
method, observation authority, required authority and memory limit must match
the execution policy even when resource usage fails. A legitimate over-limit
receipt remains a valid blocked record; changing its measurement method is
rejected with `case_gate_derivation_mismatch:...:resource_identity`.

The regression uses actual five-case execution results, then synthesizes the
over-limit observation and rebuilds its blocked aggregate before tampering.
The synthetic over-limit value is a validation test, not a measured memory result.
All **47 tests** in `tests/test_medium_scale_current_source_execution.py` passed
in 32.38 seconds after the correction. Ruff and whitespace checks passed.
Full-suite execution has not been repeated. The 1 GiB resource limit, 30-second
execution limit, numerical comparisons and independent-authority requirements
are unchanged. The prior full-suite's other resource failures remain unresolved.

Local raw artifacts: `/tmp/structural-medium-resource-regression.xml` and
`/tmp/structural-medium-gate-diagnosis-13ipp_tz/case.json`.
