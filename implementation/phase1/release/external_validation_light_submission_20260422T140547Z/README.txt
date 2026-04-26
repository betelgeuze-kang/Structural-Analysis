External validation submission bundle
Generated: 2026-04-22T14:05:48.342988+00:00
Bundle variant: external_validation_light_submission_20260422T140547Z

Contents
- external_validation_onepage.{json,md,html,pdf}
- external_benchmark_case_onepages/{index,case}.{md,html,pdf}
- validation and release reports
- signed release registry + public key + detached signature
- selected solver/parser/committee artifacts for external review

Notes
- This bundle supersedes previous bundles of the same variant.
- MIDAS parser contract records element_rows_skipped=0.
- NDTHA residual gate records hard-threshold residual trace status.
- Each external-benchmark case onepage begins with a reviewer / authority cover sheet auto-generated from the execution status manifest and KPI receipt.
- Each external-benchmark case onepage now carries bundle-local attestation template/receipt sidecars and reads a real case manifest when one exists.
- Each external-benchmark case onepage links back to the shared native MIDAS roundtrip appendix.
- release_registry.json is signed with Ed25519.
