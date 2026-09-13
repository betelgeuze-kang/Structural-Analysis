# Hosted materialization failure confirmed, 2026-09-12

Run [34695503328](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34695503328)
tests PR head `bccd81143c4fff49edd92bb3b4bda655fa0fcdca` through merge
`170339c2d78d0147b758ba6a3533d44d9e57df80`. The GitHub commit API confirms
that head and main `4de4e3f55aae1d267cf704cec7d7533f3a627498` as its parents.

Shard 1 fails evidence materialization. Both new diagnostic steps succeed and
actual repository pytest is skipped. Artifact `10297798992` contains the four
allowlisted JSON files. Its downloaded ZIP SHA-256 is
`86371d619cba46f3ea2320395f3afcf6f0406b1ce4d89f4e12cde62bbf278a32`.
This establishes hosted diagnostic retention for this failed shard; it does not
establish whole-suite acceptance. Other jobs were still running at capture.

The receipt and failure context identify the tested merge. Code comparisons
pass 10 of 12 cases; precisely two `support_N1_UX_N` metrics fail:

| Case | Product N | Retained reference N | Absolute error N |
| --- | ---: | ---: | ---: |
| `bounded_planar_member_feature_load_path` | -1.3753172320614404e-12 | 4.96422719988357e-7 | 4.96424095305589e-7 |
| `bounded_planar_prescribed_settlement_load_path` | -1000.0000000000011 | -999.9999996368755 | 3.631256504377234e-7 |

Both absolute and relative tolerances remain 1e-10. These values match the
[earlier local diagnosis](ci-replay-diagnosis-20260909.md), now confirmed in
this hosted receipt rather than inferred from gate names. The license manifest
reports `external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. Modal/buckling technical
comparisons pass, while that receipt retains partial status.

External execution is explicitly reused from historical receipts; no external
runtime executes in this generation and its historical source identity remains
unknown. The failure context does not attest receipt generation or qualification.
The matching source and replay fields support diagnostic attribution, not
independent physical validation or authenticated external provenance.

The [machine summary](ci-hosted-materialization-20260912.summary.json) records
the API snapshots, archive and extracted-file hashes in a separate local packet.
No prior sealed numerical packet, solver, tolerance or protected receipt was
modified. The earlier OpenSees arithmetic investigation remains relevant, but
a locally modified reference does not resolve the authoritative comparison gate.
