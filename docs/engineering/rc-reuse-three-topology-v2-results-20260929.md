# Three-topology RC reuse campaign: current-source repeat

This is a fixed-case development observation of deterministic Newton-assembly
reuse. It is not a learned-policy result, an independent physical comparison,
or a user-flow time saving. The frozen
[`three-topology-plan.json`](../../examples/research/rc_reuse_campaign/three-topology-plan.json)
ran at source `df20a8ac6717126ca1cbf765d25774e01f681de5` with four
counterbalanced baseline/reuse pairs per case, retained arithmetic, and
assembly timing enabled. The process exited 0. Its v2 campaign receipt has
three completed cases, no unknown native work, and a deliberately null
cross-case speed ratio. Its enclosing interval through the campaign receipt
was 227.663089302 s; this overlaps the three case intervals and is not added
to them.

| Frozen synthetic case | Baseline dispatches per pair | Reuse dispatches plus hits | Four whole-benchmark reuse/baseline ratios | Median | Earlier v1 median |
| --- | ---: | ---: | --- | ---: | ---: |
| Cantilever concrete damage | 332 | 238 + 94 | 0.800811, 0.803401, 0.800243, 0.798818 | 0.800527 | 0.797737 |
| Two-fixed-endpoint portal, 20 mm | 504 | 376 + 128 | 0.776864, 0.772894, 0.772169, 0.768272 | 0.772531 | 0.775438 |
| Pin/roller steel-plastic reversal | 186 | 160 + 26 | 0.885710, 0.885858, 0.896580, 0.900439 | 0.891219 | 0.898081 |

The saved-receipt checker re-read each of the twelve original comparison
reports, full-history checks, ordered assembly-dispatch outcomes and native
step bytes. Every baseline/reuse pair has equal native step bytes and passing
full-history comparisons. This recheck did not repeat the nonlinear solves or
establish physical accuracy. The experiment, runtime, API, assembly, and plan
Git blobs are unchanged from the earlier `fb41d86b592f2a874acedc4ae947f2a16b59fa6c`
run; the campaign runner changed from v1 to v2 interruption accounting. Each
copied model and request byte sequence was also compared with its Git blob at
`df20a8ac6`.

The complete new packet remains local at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-reuse-three-topology-df20a8ac-20260929`.
It contains 3,363 regular files and 137,276,567 file bytes (about 142 MiB on
disk). `campaign.json` has SHA-256
`521acceea00eb7ba8ed6a5397d265e555d8bcb3cf52d713890ef9d4834ea32f0`;
`plan.json` has SHA-256
`931d8639fdabedfa2bc2b2c579c2d5e08151a2e2cb79ef1c14d7acbfb8970f0c`.
[Byte-preserved copies of these two small receipts](../../examples/research/rc_reuse_campaign/README.md)
are in Git for review; the twelve original comparison reports remain only in
the local packet.
For an inventory digest, sort all regular files by root-relative POSIX path,
make an array of `{"path": ..., "bytes": ..., "sha256": ...}` records (SHA-256
of each original file), encode it as UTF-8 JSON with sorted object keys, no
extra spaces and no ASCII escaping, then hash those bytes. The expected digest
is `c242b09c12e454be4738d4224a722f920c10b8080b7da6b02d4dec8c79f3f7b4`.
This digest binds a local packet; the original 137 MB are not included in this
Git change and are unavailable to a remote reviewer unless transferred
separately.

The earlier v1 original remains locally at
`/home/betelgeuze/다운로드/rc-reuse-three-topology-fb41d86b-20260928`:
3,363 files, about 142 MiB, `campaign.json` SHA-256
`9901e3170b89de6a0a5df6f9e275de902a37bb5374c37715a53f05af9a2165c2`.
Its campaign interval was 226.543872164 s. Neither packet independently
attests that its source checkout was clean at execution; the runner records
`source_revision_is_attestation=false`. The identical native responses and
lower measured per-case times are evidence only for these fixed numerical
cases on this host. Source transport, browser review, actual engineering
costs, other structures, and independent physical verification remain open.
