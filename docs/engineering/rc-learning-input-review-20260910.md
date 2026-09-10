# Public response aliases and candidate JSON review

Two input defects are corrected while learned net savings and independent
experimental admission remain unproved. The owner's supplied review evaluated
`042896930c9f1093710d075cf0aa932883e05eec`; the defects below are reproduced
against the later local/published `66c3a1d46b5c1202a0d9c1f15147401ef793efea`.
The review's separate package execution is not counted as a run performed here.

## Measured response subsets

Source `41f59017ab6e98da029dfa4b21a66b503cb4ff83` extends the measured-source
learning split screen. Previously, a full sensor workbook and a two-column
force/displacement extract could have different original and whole-content
hashes and pass across splits after campaign labels were renamed. The screen
now also compares exact ordered, nonconstant SI displacement and force channel
pairs, independently of additional columns. Both channels must vary: a common
imposed displacement history or constant preload alone does not link otherwise
different responses. Existing campaign, original-file and whole-content checks
remain active, including for constant full histories.

The screen report is v2; existing whole-content hash construction is unchanged.
Channel hashes retain observation order and exact decimal values after unit
conversion. No interpolation, force offset, drift-to-displacement inference or
arbitrary resampling equivalence is added. Exact trajectory overlap is a
conservative rejection witness, not authenticated specimen/sensor provenance.
Same-partition aliases may pass; that is not additional independent data credit.

An actual observation uses the already acquired SERA-ARISTA unretrofitted
workbook, SHA-256
`8777616e2d0aeb24dec9d6b0de7f8706293013479d37b9cc2fd093f8ec6706ee`.
An explicitly local audit derivative retains only A/B and deliberately changes
campaign/specimen/test labels. It is not a separately discovered public source.
Direct XML extraction verifies all **8,118 original tokens** in the two columns
and independent rational arithmetic checks their SI correspondence across all
**4,059 rows**. The complete source has 116 columns, including its index.

The old implementation accepts the full/subset cross-split pair. The correction
rejects both encounter orders and rejects the pair through the actual learning
entry before compile, structural execution, fitting or study output. That entry
uses a placeholder authored model solely to test preflight; it does not pair
ARISTA with a physical model. Same-training-partition use passes. Original bytes
remain unchanged; no measured specimen is admitted to training.

The observer completes in 11.100272 s internally (CPU 11.061635 s; peak RSS
514,728 KiB), including decoding and repeated old/new checks. Each of the three
new rejection screens costs approximately 1.55-1.56 s on this shared host.
There are zero structural calls and zero fits in this observation. The test
selection first passes 53 tests in 1.99 s, then the expanded selection including
actual authored learning paths passes **90 tests in 150.03 s**; these selections
overlap. Ruff, scoped mypy and diff checks pass.

Sealed packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-measured-subset-30vb7o_e`,
17 files / 6,383,403 bytes, inventory SHA-256
`cd5642fa7cff7097cdfcbce9ced6ce5b0f7bb108d4aad42f3538e9e08192b5ae`.
The source, audit script, original, derivative, previous implementation,
rejections and successful terminal parent record are retained and reread exactly.

## Candidate policy and training report JSON

Source `4d345a423b7a4ab1acba4d03fe8c118756526f1c` uses the existing
`strict_json_object_bytes` parser for the candidate policy constructor and the
CLI's historical training report. Both enforce a 2 MiB UTF-8 byte limit and
reject duplicate keys, nonfinite numbers and malformed/deep JSON before their
semantic contracts are used. Parsing a previously validated canonical in-memory
policy in `to_dict` remains unchanged.

Using the existing actual CLI-generated Workbench policy, the previous loader
accepts five ambiguous probes: a conflicting ridge prefix, equal-value duplicate,
escaped spelling of the same key, duplicate keys inside a subsequently overwritten
object, and a NaN subsequently overwritten by the legitimate ridge. Each resolves
to the original policy hash. The corrected loader rejects all five and preserves
the normal policy dictionary and hash. This reproduces an ambiguous transport
boundary, not a bypass of final structural verification or a changed learned model.

The candidate suite passes **32 tests in 11.34 s**, including actual small
training/search paths, duplicate policies and duplicate training reports rejected
by the CLI before search/output. Ruff and scoped mypy pass. The separate
five-probe original-policy observation takes 0.027919 s and invokes no fit or
structural solve. No performance improvement is inferred from these checks.

Sealed packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-candidate-json-ylgj19db`,
18 files / 435,028 bytes, inventory SHA-256
`acd2c8e8f13474cc6f6dcd00381103930f805667cda3a3cc9669e49bb1aecae0`.
It retains current and previous source, the original policy, all five probes,
outcomes and the targeted CI records below.

## Current-source integration evidence and next work

For `66c3a1d46`, original job metadata and logs are inspected for
[full-test shard 0](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34425568040/job/102709951535),
[legacy contract-core](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34425567978/job/102711661061)
and the [structural verifier](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34425568074/job/102709951289).
All fail in exact-source evidence materialization and skip their subsequent
test/verification step. The full-test and legacy logs explicitly identify
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready` at the due-diligence command.
These are current-head observations, not an assumption that an older failure
recurs. They do not isolate the numerical root cause of the failed external replay.
No workflow, receipt, independent tolerance or final acceptance gate is weakened.
This is not a full-suite pass for the two new implementation commits.

The attempted Zenodo 1205887 metadata request returns HTTP 504; the web reader
also times out. Its single-record failure packet is sealed separately as
`structural-continuous-rc-source-pbyhayvc`. No new file, license clearance or
compatible specimen is inferred from that attempt.

The review's priorities remain open: diagnose the exact external replay failure;
report selected-versus-exhaustive minimum feasible common-price cost only when
the required results are verified, with unknown retained otherwise; evaluate
runtime-relevant strategy decisions on leakage-resistant cases; reconstruct
experiments compatible with the implemented physics; and measure total user-flow
cost. A finite candidate-pool cost comparison would not establish global design
optimality. The full roadmap, independent validation, licensing, owner/hardware
dependencies, learned advantage and release approval remain incomplete.
