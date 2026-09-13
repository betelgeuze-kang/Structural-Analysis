# Candidate-search process resources

## Implementation and measurement boundaries

`fiber_frame_candidate_process` accepts a strict JSON suite declaration and
snapshots model/training bytes before execution. It validates the frozen training
report and prepares both online plans for every case before the first worker.
The plan hash binds the source, model, configuration, prices, terminal/history
limits, pool, policy and shortlist. This repeats bounded preflight/prediction
work in the parent; the parent's cost includes it.

Each case, phase, repetition and strategy runs in its own fresh Python process.
Deterministic and learned arms alternate order by round and case index. Each arm
prepares its own inputs and makes its own fresh baseline and shortlisted full
reference requests. Deterministic and oracle workers do not call the predictor.
An optional exhaustive oracle starts only after both online reports validate;
its requests/resources are retained separately. Workers never collect labels or
fit the preserved policy. Historical generation/fit wall costs and requests are
charged once per distinct training-report hash, including across cases.

The parent validates stored raw artifact identities and nested original public
result, quantity, price, history, selection and request-count contracts without
another solve. Failure rows cannot reduce executed-request subtotals by changing
the envelope around their original solver metrics. A physically rejected candidate
can retain valid measured resources. Invalid reports, missing resources, timeouts,
changed frozen inputs and duplicate worker IDs remain explicit failed slots;
unknown counts and incomplete CPU totals stay unavailable. Partial raw files are
preserved. Input failures before complete read coverage may retain raw CPU data
without receiving validated aggregate resource credit.

- Worker workload wall/CPU includes preparation, ranking, full reanalysis and
  selection. Whole worker CPU starts at process creation and ends after search
  report persistence, before resource-sidecar emission.
- Per-worker Linux `VmHWM` records the post-exec address-space peak, including
  imports and report encoding. Separate-process peaks form distributions and are
  never added or subtracted. Unsupported peaks stay unavailable.
- Input byte/read timings describe bounded file API reads; report encode and
  write/flush/fsync timings describe `search.json`. These are not physical disk
  traffic and exclude resource sidecars, manifests and final parent-suite I/O.
- Parent wall/CPU includes snapshot preflight, launch/wait, validation and final
  aggregation, ending before suite encoding/persistence. Preflight is a subset.
  Parent wall includes child waiting and cannot be added to child wall. Parent
  and worker CPU cover disjoint processes; historical CPU was not measured.
- Each parent slot also records elapsed wall and parent CPU around request
  persistence, worker launch and parent validation. Paired elapsed comparisons
  use this complete slot. Shared preflight and final aggregation remain outside
  the pair; any positive-median reuse projection is conditional on that scope.

Source IDs and hashes establish local consistency, not source attestation or
independent numerical authority. The shared legacy in-process comparison retains
its public schema, arm order and clock-call boundaries. Usage and a portable
two-pool example are in `rc-fiber-design-experiments.md`.

## Correctness verification

The first integration fixture completed nine fresh workers: one warmup and two
measured repetitions of a single pool, with a later oracle for each pair. It made
21 new full reference requests and charged four historical requests once, total
25, with no policy retraining. All workers were ready and the initial 36 tests
passed in 219.20 s. Files are retained under
`/tmp/structural-candidate-process-za6sdcpy/`; that correctness execution overlapped
development and is not performance evidence. Its suite predates the added parent
slot timing fields, while its raw worker reports remain usable for validation.

Saved artifacts then passed 110 request/plan/resource/failure contract checks in
4.03 s without additional solver calls, including six blocked execution-count
receipt probes and one controlled-clock parent-slot timing probe. Shared runtime/learning-process regression
passed 51 tests in 6.09 s (eight numerical tests deselected). Existing candidate
suite/history regression passed 82 tests in 14.74 s; legacy arm/order/binding
contracts passed 33 tests in 1.74 s (nine unrelated tests deselected). CI ownership
and quality-gate contracts passed 34 tests in 0.36 s. These separate groups
overlap and their counts are not summed. Ruff/format and `git diff --check` passed.
The documentation's two-pool request also passed frozen-plan preflight with worker,
solver and training entry points explicitly forbidden.

## Fixed-source observation

The driver ran at clean source
`b4681eeabbaccb7cce3eedc491dc2fcd0f194444`, checking exact HEAD and empty tracked/
untracked status before and after the interval. All other agent tests and edits
were stopped; only bounded read-only inspection continued. Artifacts, driver,
protocol, CLI log, frozen inputs, worker files and receipt are preserved under
`/tmp/structural-candidate-process-observation.5TRGr2/`.

The host reports AMD Ryzen 9 5900X, 24 logical CPUs, Linux 6.5.0-26-generic,
Python 3.10.12, NumPy 1.26.4 and SciPy 1.12.0. Exclusive host access and independent
hardware/operator acceptance are not asserted.

The observation reused the original four-label training bytes from source
`412fda612e442368da0ee3b0add743654d3fdc8d`, without regeneration or fitting.
Pool A uses widths 0.400 m baseline, 0.360 m narrow and 0.395 m near-limit; pool B
uses 0.405/0.380/0.399 m. These are two pools in the same synthetic 3 m cantilever,
FY=-1 kN, two-step monotonic family. Both separately typed terminal and committed-
history screens use the preserved train-only mean labels: translation
`4.551020408163264e-5 m`, absolute strain `2.991063860793252e-6`. The declarations
and plans were frozen before any online request.

Each pool ran twice with alternating online order, zero warmups, budget two
requests per online arm including its own baseline, and a later three-request
exhaustive oracle. All 12 distinct workers and 28 new full reference requests
passed: 16 online and 12 oracle. Four historical requests were charged once,
giving 32 accounted requests. There were no unknown executions, skipped slots,
timeouts or unavailable resource sidecars.

Every deterministic arm selected baseline; every learned arm selected the fully
verified `near-limit` candidate. Per pool, deterministic missed a feasible
candidate in both oracle audits; learned missed none and had zero terminal
false-safe/predicted-safe-unverifiable cases. These repeated observations do not
create independent candidates or a history-safety predictor. Synthetic prices of
100 per gross concrete m³ and 1 per authored straight rebar kg, labelled KRW, give
pool A estimates 144.9108 baseline / 144.0108 selected and pool B 145.8108 /
144.7308. They are fixture estimates, not quotes or construction savings.

## Observed costs

The paired deterministic-minus-learned slot differences are **-0.638848 and
+0.101082 s** in pool A, and **+0.252047 and -0.150749 s** in pool B. Both change
sign across repetitions, so this observation does not establish consistent
acceleration. Paired medians are -0.268883 s and +0.050649 s, respectively.
Pool B's arithmetic projection of 761 reuses assumes that small positive median
persists for the same training artifact and excludes shared preflight/final
aggregation. It is not an observed or statistically established break-even.
Pool A's projection is unavailable.

Slot time includes parent request persistence and validation. Each row contains
two observations; population SD is descriptive, not an uncertainty interval.

| Pool | Strategy | Slot wall median (s) | Min–max (s) | Population SD (s) |
| --- | --- | ---: | --- | ---: |
| A | deterministic | 23.238455 | 23.238205–23.238705 | 0.000250 |
| A | learned | 23.507338 | 23.137123–23.877554 | 0.370216 |
| B | deterministic | 23.488750 | 23.337678–23.639823 | 0.151073 |
| B | learned | 23.438101 | 23.387776–23.488426 | 0.050325 |

The following distributions cover four separate workers per strategy across the
two pools. CPU is summed across disjoint workers; peak RSS is not summed.
The oracle makes three requests per worker and retains a different report shape
from the two-request online arms, so its peak is not an equal-workload advantage.

| Strategy | Full requests | Worker CPU sum (s) | Peak RSS median (MiB) | Peak RSS min–max (MiB) |
| --- | ---: | ---: | ---: | --- |
| deterministic | 8 | 92.627121 | 107.298828 | 106.835938–107.808594 |
| learned | 8 | 93.015304 | 107.750000 | 107.367188–108.160156 |
| oracle | 12 | 136.029886 | 105.810547 | 105.734375–106.117188 |

File API observations below use the same four-worker groups. They are subsets
of the recorded CPU/wall scopes and are not added again.

| Strategy | Input bytes | Read time (ms) | Search report bytes | Write/flush/fsync (ms) |
| --- | ---: | ---: | ---: | ---: |
| deterministic | 144,684 | 0.688157 | 2,645,378 | 27.077951 |
| learned | 144,660 | 0.687448 | 2,644,548 | 26.791256 |
| oracle | 145,408 | 0.725240 | 1,514,836 | 24.957572 |

- Parent wall through aggregation: **324.233385 s**, including child waits.
- Whole CLI launch-to-exit wall: **325.915810 s**, including interpreter startup,
  imports and final suite encoding/persistence; excludes driver setup and post-run
  validation/export. These overlapping wall intervals are not added.
- Worker CPU subtotal: **321.672311 s**. Parent CPU: **0.572932 s**, giving
  **322.245242 s** in disjoint current process scopes. Resource-sidecar emission
  and final suite serialization remain outside those CPU endpoints.
- Parent preflight: **0.061832 s wall / 0.056553 s CPU**, already included above.
- Historical generation **38.517924 s**, fit **0.001512 s**, charged once.
  Parent wall plus historical wall is **362.752822 s**; historical CPU is unknown.
- The outer driver's own launch/wait CPU is **0.076377 s**, separately scoped;
  it does not represent CLI parent or worker CPU.

The saved eight original measured comparison bundles passed the current
Workbench manifest/report parser, including byte length/hash and source bindings.
Exports retained the original nested producer JSON and added no solver requests.
This is parser acceptance; desktop/mobile rendering was not repeated for this
unchanged comparison schema.

## Comparison with the earlier history observation

`parity-check.py` compared all 28 rows with the preserved source-`cc45b3449`
history experiment, without solving again. Every public result field other than
`input_checksum` and its enclosing `result_hash` is exactly equal. Candidate
result hashes match in all 16 candidate rows. The 12 baseline result hashes differ:
the older driver reconstructed compact JSON input, while this request loads the
preserved pretty-printed baseline bytes. Both checksum paths were reproduced and
match their recorded inputs; canonical model identities and physical values match.
This is an input representation difference, not evidence of a changed response.

All 28 stored checkpoint descriptors agree, including artifact hash/byte length,
chain/root/terminal state identities. Both observations lack separately retained
raw checkpoint files, so this audit does not claim a direct checkpoint-byte
comparison. Low-level history objects and all 56 positive epoch identities agree;
both engineering maxima occur at epoch 2. All 28 reference/history rows verify,
with 20 rows passing the screens and eight narrow rows failing. The eight online
selections, rankings, shortlists, physical performance, material estimates and
deltas also match. This does not establish between-step extrema or independent
physical validation.

The structured `parity.json` is 341,573 bytes, raw SHA-256
`a02d87031ea7f9eb768be943726f41f1aeac231edfbe09cd1046bfd82d7971dc`.
All source files read by the audit retained their original byte hashes.

## Artifact bindings

Suite logical report hash:
`sha256:83ff874ee1a83913850ff040d841e315dd14e25aa6f571157e001fe89f8c3491`.
Training logical report hash:
`sha256:65f47bd2d42c64fcf643b176311c76ddfdd4ba58560a11e1e2bf8bd9b4e8bd60`.
The unchanged Workbench schema source hashes to
`sha256:126eecabef65b2b83bae80c5cb1ee1d1a5e58c16bbccd9028444149af7b0d79c`;
the parser ran with the repository-verified Node v24.20.0 binary.

A separate local resource audit completed 801 consistency checks with no
mismatches, covering original and frozen inputs, manifests, raw report/resource
bytes, 12 distinct PIDs and recomputed request/CPU totals. Parent slot CPU sums
to 0.515855 s within the parent total; slot wall sums to 324.171015 s within parent
wall, with each slot including its launch interval. This audit added no solver,
training or test execution and provides no external attestation.
`resource-audit.json` is 26,598 bytes, raw SHA-256
`d0e9e79875b378f7721558b31f6b59559cdfb6920896327ccc2132876ea9081c`.

| File under the observation directory | Bytes | Raw SHA-256 |
| --- | ---: | --- |
| `run.py` | 8,174 | `3c77099006728a789da755db83e3f1b254e65ad50f877fa26e2557db32f35f21` |
| `protocol.json` | 1,969 | `5e11e505594b2fa45ec113dd7ad271c653b77fa2250232688c532f71c68d4dd7` |
| `request.json` | 3,381 | `709523bbfeb1931009240f5d01c6cd7910e369f535329f8bb44b9c9834d16cf6` |
| `training.json` | 31,759 | `7654095ce46654a6a59865131ec4199696bdc677f31f62a595374cbe78d8c605` |
| `suite/suite.json` | 7,754,233 | `6539106620d6868abf8944b198c508b8eb1693302948013baefb84aa7d204dea` |
| `receipt.json` | 36,712 | `9e672f3983d00f5851fe6a798ef452b72596668b514b83de844c5d00d08c8645` |
| `parser-receipt.json` | 2,653 | `1a5d8e15a0145347787fe936fef9f72b2cc450fc872a745f630fd8672d420ac0` |

The final `artifact-manifest.json` inventories 123 preserved files totaling
17,305,975 bytes, excluding the manifest itself. It includes every worker file,
the eight exported bundles, both post-run audit scripts/results, parser artifacts
and separately scoped correctness logs. A second byte pass verified every entry
and exact file coverage. The manifest is 22,965 bytes, raw SHA-256
`0b767212bc8cb12e55c244de7b2e0e23b20422c88619523517a530c62d118297`.
Implementation, test and CI sources remained identical to the measured commit;
the subsequent commit changes only this record and the implementation register.

## Remaining work

Independent corpus/provenance/licensing, larger geometry/load-history families,
repeated hardware/operator acceptance and hosted integration/review remain open.
Local timing, fixture prices and hash validation do not establish generalized
acceleration, construction savings, design-code compliance or release approval.
