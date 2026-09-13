# Current-product replay diagnosis, 2026-09-09

At source `a62ee3edf5cc78ae9b3b9ac5090d53533bd7dfb5`, refreshing copied
external receipts reproduces two failed code-to-code comparisons. This explains
the license inventory blocker seen during AI CI evidence materialization;
`product_legal_approval=False` is an expected non-promoting value, not itself a
failure. This is a local reproduction, not a new hosted CI result.

Unrefreshed license aggregation passes on both the AI source and R2 source
`f788a3c55964ef963f8145835e188d4a3f3792da`. Current AI product replay passes
10 of 12 code-to-code cases and both modal/buckling cases. The two failing
metrics, each `support_N1_UX_N`, are:

| Case | Current product (N) | Retained reference (N) | Absolute difference (N) |
| --- | ---: | ---: | ---: |
| `bounded_planar_member_feature_load_path` | -1.3753172320614404e-12 | 4.96422719988357e-7 | 4.96424095305589e-7 |
| `bounded_planar_prescribed_settlement_load_path` | -1000.0000000000011 | -999.9999996368755 | 3.631256504377234e-7 |

All other metrics in these cases pass. These differences exceed the original
fixed comparison tolerances; their small magnitude does not justify converting
failure to acceptance. No solver force, reference value or tolerance was changed.
Determining whether the difference originates in reference arithmetic or current
product behavior still requires focused attribution and reference verification.

Aggregation with refreshed copies exits 1 with exactly:

- `external_code_to_code_product_replay_not_passed`
- `external_code_to_code_technical_receipt_not_ready`

Both replay CLIs themselves exit 0; their payload's technical pass flags must be
inspected separately. Code replay takes 154.679729607 s parent elapsed time and
modal replay 4.347561552 s. NumPy 1.26.4 and SciPy 1.12.0 match the CI pins;
the explicit worktree `src` is selected by `PYTHONPATH`, with Haswell OpenBLAS
and one BLAS/OMP thread.

The local diagnostic packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-ci-license-replay.1t45cnyu`.
It contains original receipt copies, refreshed copies, unrefreshed and refreshed
license aggregation, commands, source protocol and process logs. The accompanying
[machine summary](ci-replay-diagnosis-20260909.summary.json) binds file hashes,
failed metric payloads and process results. Protected repository receipts and
completed learning/source packets remain unchanged.

External execution is reused from the historical receipts; no external engine
runs in this generation, no freshness or independent-validation credit is added,
and unknown historical source identity remains unknown. This diagnostic neither
closes full CI acceptance nor changes legal/release authority. The full roadmap
remains open.
