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

## Observation protocol and remaining work

The fixed-source observation will reuse the preserved four-label training report,
two declared pools from the earlier history experiment, two measured repetitions,
zero warmups and both terminal/committed-history screens. It declares 12 workers,
16 online and 12 later oracle requests; four historical requests are charged
once, giving 32 accounted requests. Other tests and edits must stop during the
measurement. The CLI interval and post-run byte revalidation/bundle exports have
separate boundaries. Reusing inputs does not create new independent cases.

Independent corpus/provenance/licensing, larger geometry/load-history families,
repeated hardware/operator acceptance and hosted integration/review remain open.
Local timing, fixture prices and hash validation do not establish generalized
acceleration, construction savings, design-code compliance or release approval.
