# Completed hosted diagnostic lanes at 5a0def376

The [original-log receipt](hosted-5a-completed-ci-20260914.json) records selected
terminal jobs for published head `5a0def37655a095c2bd25028b0be74142a6eebe2`.
Run metadata binds every job to that head before capture. This does not cover
the later local strict-string optimization, repeated UI comparison or quadratic
seed studies.

| Lane / original job | Observed result |
| --- | --- |
| Repository development contracts / 103753935641 | 1,176 passed in 1,103.94 s |
| Runtime frontend contracts / 103753935711 | 704 passed in 10.2 min; separate HTTP suite 26 passed in 2.0 min |
| Runtime Python contracts / 103753935857 | 96 passed in 13.91 s |
| Full shards / 103753935783, 103753935784, 103753935803, 103753935842 | all fail materialization; actual repository test execution skipped |

Each shard log names both `external_code_to_code_product_replay_not_passed`
and `external_code_to_code_technical_receipt_not_ready`. Each also contains a
single passing preparatory test; that is not an executed full shard. These
failures do not establish a new numerical root cause beyond the retained
upstream evidence dependencies. No tolerance, external receipt or acceptance
rule was changed in this capture.

All seven selected jobs are terminal. The separately followed topology job
103753935207 was still running in its regression-neighborhood step when this
capture was made; it is not reported as passed here. Nor is the full repository
suite or current main qualified by the successful diagnostic lanes.

Original two-run metadata, seven job metadata records, seven logs, capture
script and summary total 18 files / 717,504 bytes. Every file was reread against
the SHA256/length inventory before sealing. The receipt retains exact GitHub
job/run identifiers and original result lines. Test counts from different
lanes are not presented as a disjoint total. No new numerical solve or fit
was performed to capture these logs.
