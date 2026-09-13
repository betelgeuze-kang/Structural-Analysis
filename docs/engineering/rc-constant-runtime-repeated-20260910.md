# Completed constant-loaded RC repetitions

The [two-topology pilot](rc-constant-runtime-pilot-20260910.md) admitted three
fresh repetitions per authored case. All repetitions and their original-record
audits now finish successfully. Numerical source remains frozen at
`4a79207f8`; original-record audit source is `6b41880a9`. No model, target history,
constant load, arithmetic profile or comparison tolerance changes during measurement.
Reference/secant order follows the predeclared alternating schedule; every pair
is followed by a fresh reference run, and every case pair by separate audits.

**All six fixed reference/secant comparisons pass. All 18 paths complete their
preload and 242 lateral targets.** Every repeated original step matches the pilot
bytes: 4374 exact step pairs, including 18 preloads. All 18 complete
preload/response-history/native-checkpoint pairs also match the original pilot.
These are original-record consistency results for authored nonlinear cases, not
experimental physical validation or learned-model acceleration.

| Case | Reference median [min, max], s | Secant median [min, max], s | Median paired reference/secant ratio |
| --- | --- | --- | --- |
| Cantilever | 18.298283 [18.221831, 18.516095] | 15.265312 [15.216935, 15.455254] | 1.198045 |
| L-frame | 100.547779 [100.223057, 101.282491] | 72.786860 [72.560450, 73.887636] | 1.376939 |

Secant is faster in all three observed pairs for both cases. Median paired time
saved is 3.032971 s for the cantilever and 27.436196 s for the L-frame. Reference
sample standard deviations are 0.152686 s and 0.542778 s; secant deviations are
0.125972 s and 0.709975 s. These are three samples per case on one shared host with
explicit one-thread BLAS/OpenMP settings. No confidence interval, dedicated-host
measurement, general speedup or learned-policy benefit is inferred.

## Original solve, correction and separate audit costs

The repeated numerical studies charge **4374 core calls, 18672 Newton iterations
and 18672 linear solves**. Included terminal polishing performs 8097 attempted
corrections and assemblies, with 5793 accepted corrections and additional linear
solves. There are no reported polishing assembly/linear exceptions. Polishing is
already included in the original solve counts and timings; it must not be added
again as a separate Newton cost. Rejected corrections remain charged.

The six separate original-record audits reconstruct another 4374 constitutive
assemblies, with 201204 recorded material integrations and 4374 rational
force/tangent record rebuilds. They perform zero new Newton solves and zero state
commits. These checks reproduce source behavior and recorded arithmetic, rather
than introducing an independent physical oracle. Their cost is retained separately.

| Nested timing scope | Seconds |
| --- | ---: |
| Six numerical processes, including startup/output | 1005.842007 |
| Six complete in-process studies | 995.017410 |
| All 18 complete paths | 981.394757 |
| Original core invocations inside paths | 800.422705 |
| Proposal computation inside paths | 3.528474 |
| Original response recovery inside paths | 137.360333 |
| Six separate audit processes | 285.173209 |
| Audit routines inside those processes | 274.342481 |
| Whole repetition driver, including setup and audits | 1291.172464 |

Rows describe nested scopes and must not be summed. Per-arm CPU, wall time, known
work and all raw samples remain in the [machine summary](rc-constant-runtime-repeated-20260910.summary.json).
The repeated costs are additional to the separately reported pilot and focused
tests. No fit is performed in this experiment, and no external sample is admitted.

## Aggregate verification and retained packet

`scripts/summarize_rc_constant_repetitions.py` verifies the complete declared
three-repeat/case/audit schedule, fixed source/input identities and arm ordering,
then rereads each original path and step. Step counters must agree with original
Newton metrics; clocks are rebuilt from original preload, proposal, solve and
recovery records. Separate audit integration counts must match the recorded fiber
point coverage. Unknown work, incomplete paths, altered step bytes or inconsistent
costs prevent qualification. Signed time regressions remain visible in dispersion.
Recorded process/audit receipts do not authenticate their producer.

Ten focused tests pass in 0.26 s, including missing/duplicated repetitions, failed
or missing audits, invalid exit-code types and preload-inclusive timing bounds.
Ruff, formatting, mypy and diff checks pass. The positive aggregate runs once on
all completed originals and passes in **11.648307752 s**, with no new structural
solve or fit. It executes from a retained working-source copy subsequently
verified byte-for-byte against commit `d176f42f3ee7b325b62a7eeb55a8b11570eb20fb`.
The earlier prepared aggregate copies remain as history; they are not additional
positive runs. Source package copies remain exact to all 429 original Git blobs.

The repetition driver and aggregate execution handles both finish with exit zero.
All 17 recorded pilot/repetition worker, audit and stage-driver PIDs are absent
before sealing. The complete packet is now sealed at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-constant-runtime-6fw_tfsz`:
**35607 files / 1192568564 bytes**, inventory SHA-256
`e3b1a6a8c4db5cdc7a45838d9da2d16cb5561c9255cae282173a53d5bf4fcb63`.
Every file is reread exactly; sealing takes 3.481451250 s. Originals, source copies,
process outcomes, audits, complete costs, negative-test results and hosted receipts
remain retained. No process is restarted or output directory reused.

## Hosted and roadmap boundaries

At published head `9793cf938`, Frontend Web CI 34405039196 and Viewer Browser CI
34405039085 finish successfully. Main CI 34405039231 fails at the external evidence
materialization prerequisite. Two repository-test shards are terminal failures at
inspection, while two remain running. Three retained original logs name
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. Their detailed metadata and
logs remain under `hosted-9793cf938`; these are not Python assertion failures.

Issue State Current succeeds through its offline job; `live-exact-main` is skipped
on the PR branch and does not prove current-main closure. Supplemental PR #440 is
still an open draft at `f788a3c55964ef963f8145835e188d4a3f3792da`, unmerged against
main `4de4e3f55aae1d267cf704cec7d7533f3a627498`. No main, signature or owner gate is
changed by this observation.

The complete roadmap remains open. This establishes a repeated deterministic
baseline for constant-loaded authored cases. Independent experimental reconstruction
and reuse terms, leakage-resistant external training admission, learned net benefit,
broader capability and independent/hosted/owner acceptance remain separate work.
