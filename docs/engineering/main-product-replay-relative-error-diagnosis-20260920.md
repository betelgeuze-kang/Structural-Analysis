# Main replay rejection isolated to derived relative-error fields

Read-only inspection of official artifact 10334556078 from clean-runner run
34808440032 finds a receipt claiming fresh external execution at main
`234c3122c78dea064411aa16b06b18ab16157576`. Its clean-runner summary claims
same-operator container-isolated reproduction, but explicitly does not claim
independent operator attestation, redistribution/legal approval, verification
level 2 or release readiness. This inspection is not new signature verification.

Main Product State job 105789490226 fails with
`receipt_product_comparisons_stale`. To investigate without replacing evidence,
tracked main src/scripts/examples/pyproject were archived into a separate
scratch directory. The original downloaded receipt was preserved. The main
implementation of `_current_product_comparison_cases` was run on local CPU
and compared using its unchanged `_product_replay_values_match` predicate.
Runtime was 76.028009477 seconds. This is a local main-source replay, not an
exact recreation of the hosted environment or a fresh external solver run.

The local rejection has exactly two differing leaves under the existing replay
predicate, both case index 3 (`bounded_planar_member_feature_load_path`):

| Metric | Stored product | Current product | Stored relative error | Current relative error |
|---|---:|---:|---:|---:|
| support_N1_UX_N | 4.964233584953451e-7 | 4.964244685421869e-7 | 1.2862162879701057e-6 | 3.5223082254989975e-6 |
| member_E1_end_j_MZ_N_m | 4.440892098500626e-13 | -1.3322676295501878e-12 | 1.9958403095347198e295 | 5.987520928604159e295 |

Both metrics' original and replayed `contract_pass` remain true. The external
references are 4.96422719988357e-7 N and exactly zero N m. Absolute errors are
below the existing 1e-10 absolute tolerance. For zero reference the relative-error
formula divides by the smallest normal float64, producing enormous diagnostic
values from near-zero absolute responses. Comparing those derived values for
replay freshness can reject otherwise accepted primitive response drift.

This isolates a concrete local rejection mechanism; the hosted job did not emit
individual differences, so these exact two leaves are not asserted as its proved
complete cause. The development branch's separate external comparison failures
must not be conflated with this main-source replay. No tolerance, predicate,
receipt flag or source code was modified. Next work should examine consistency
validation of derived metrics and numerical identity separately, preserving
primitive-value, contract-result and provenance checks.

Evidence directory:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-main-replay-50839mre`.
It contains the archived main source, original external artifact ZIP and receipt,
replay comparisons, mismatch paths and the execution script. External inventory
SHA-256: `31cf334f71b314ae6923943b3391ce4bfc759f32fde5356d463614ccf5d7d798`.
