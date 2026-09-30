# Staged screening with observed material nonlinearity — 2026-09-13

The recent small-displacement layout observations did not by themselves establish
screening utility after material yielding/damage. This campaign adds two larger
fixed displacement histories and checks actual material response as well as full
execution costs and retained histories.

## Preregistered numerical scope

Clean source `d7b173a9ddf10e16cf74373dc31f5040a1f78ce3` was archived before execution.
The existing five-model pool and synthetic price table were retained. All six
original displacement targets were multiplied by 1000 or 1500, respectively, giving
maximum requested absolute control displacements of 0.02 m and 0.03 m. The common
maximum absolute fiber-strain screen was set to 0.003. Complete generated requests,
the explicit strain limit and fixed two-target prefix were recorded before the first
solve. Other limits and the five-model consideration horizon were retained. These
limits are experimental caller inputs, not approved design criteria.

Both conditions ran pruned then staged and staged then pruned in sequential separate
processes, without automatic retries. The original small-amplitude outcomes were
known; the new outcomes were not inspected to choose these settings. There were no
policy fits, predictions or new training labels. This is price-order scheduling.
The cases share a model pool and history shape; they are not independent projects
or structural systems. The host was not isolated.

## Material response and paired work

All 22 full result rows passed the existing complete internal reference verification
and exhibited nonzero accumulated steel plastic strain or concrete tensile damage.
For example, at multiplier 1000, baseline maximum accumulated steel plastic strain
was 0.0024565503343299067; the selected middle candidate had
0.0008639406744319056. At multiplier 1500, the selected large candidate had
0.0012581413719350426. Preserved material metrics make this a material-nonlinear
observation rather than an inference from the solver's name. They do not establish
experimental accuracy or validate the small-displacement element outside its scope.

| Multiplier | Full-selected candidate in every run | Pruned full / staged full + prefix rows | Newton/linear solves per pruned / staged execution | Staged/pruned process ratios |
|---|---|---|---|---|
| 1000 | middle | 3 / 2 + 2 | 218 / 208 | 0.960523, 0.967369 |
| 1500 | large | 4 / 2 + 3 | 294 / 240 | 0.845972, 0.841715 |

Per-condition ratios of summed process times were 0.963949 and 0.843842
(about 3.61% and 15.62% reductions). With only two ordered repeats per related condition,
these are observations without confidence intervals or generalized speed claims.
The earlier 0.6-amplitude observation was slower with screening, so this result does
not justify an unconditional prefix strategy. It also does not demonstrate learned
benefit: no AI participated in these decisions.

All eight worker processes exited successfully. Across them there were 22 full and
10 prefix rows, 64 API invocations, 304 attempted steps and 1920 Newton/linear solves.
Candidates accepted by a prefix still ran full fresh analysis and verification;
prefix-only rows never became incumbents. No exhaustive pool oracle was run, so the
results do not claim an independently computed pool-wide optimum or real cost savings.

## Original audit and accounting

The no-solver audit checked the exported Git source, inputs, quantities/common prices,
request bindings, result/checkpoint/verification identities, response-derived limits,
366 artifact references, 40 cost decisions and ten prefix decisions. It recomputed
all reported work. Fifteen repeated full records matched exactly in request, complete
response history, terminal response and checkpoint; ten prefix histories exactly
matched their corresponding full history prefix. There were seven distinct full
case/model pairs, not 22 independent specimens.

The campaign parent interval was 146.864048953 seconds; the separate audit was
2.727357554 seconds. Individual process times include startup through exit and original
record persistence. Input/source preparation, later audit and HTTP/UI work are
excluded. Inner intervals are not additional to the parent time.

Sealed packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-layout-staged-nonlinear-_z7gem9v`.
1139 files, 150268719 bytes; inventory SHA-256:
`da2df2ad930653cdfa0d0b7d6420f0c446391322f5079d16ca8e28446b0cc981`.
The summary preserves all timings, work counters, material metrics and qualification
flags. No earlier packet or protected verification receipt was modified.

## Completed hosted CI observation and publication continuation

The previously awaited [Repository Python Tests run 34723974528](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34723974528)
has now terminated at `dea625b1a023954a3c2f7a39168f9f55cddcdc6a`.
Development contracts passed **951 tests in 867.49 seconds**, and collection passed.
All four full shards failed external comparison materialization before their actual
full test commands, and the aggregate failed. The four original failure logs are
bound in the installed-wheel observation. This remains a full-suite non-pass.

The earlier native clean-install run completed its Linux/Windows build/install,
platform comparison and packaged browser checks successfully; its main-only signing
jobs were skipped for the PR event. Those bounded installation successes and the
failed repository-wide gate remain separate. They do not qualify the later CLI or
this later numerical source as fully accepted by hosted CI.

With all those jobs terminal, the previously held amplitude, CLI and wheel records
can be published together without cancelling that execution. Independent physical
verification, leakage-resistant learned net benefit, broader structural capability
and the remaining owner/licensing/hardware gates are still open.
