# RC committed-material capture cost: synthetic development result (2026-09-29)

The opt-in, path-local layout cache retained every checked proposal context,
guard context, and step byte, but did **not** reduce committed-material capture
time in this F/G development cohort. The six uncached paths spent `0.229831946 s`
on 54 captures; the six cached paths spent `0.235190124 s` on 54 captures.
Cached capture was slower in five of six matched pairs. The predeclared
equal-case whole-path proposal/secant diagnostic ratio was `0.9979186267`
uncached and `0.9932604598` cached. Both **fail** the strict `<0.99` screen.
Secant remains the selected strategy; no learned policy is promoted.

## Frozen numerical run and correction

The numerical source was clean commit
`5187de5fab1e5d4403c9f8191568e2dd8ffec4a6`, stacked on draft #496 head
`82d1510c2b42ef56ef7f837af2c710b5fe9b4db9`. The plan was written before
its first slot: plan hash
`sha256:a9fdd4f8c802daed15a920bbb24d6a6e76d86e8fd7a8c5fe30101f9a7fbd28b3`,
file SHA-256 `9b927f118301357f2425cff3e2ce512ec288db60c4e444550a53e877b371dc44`.
It bound the original non-reserved packet inventory SHA-256
`e47a96cf34c52b3a088f15eba08a890e745da6096a7a43b5127f78df8ca2b7c0`
and frozen unpromoted policy
`sha256:748ca448dc4aacea36bea9d6672057aa3d76c15ff1d8ac6db6f9ff53e40e8e48`.
Only A–E training metadata and synthetic F/G development inputs were read.
No reserved case was read or executed.

All twelve declared slots completed in index order, each in a fresh Python
process, with reference, secant, guarded proposal, and fresh-reference full
paths: 48 paths in total, zero warmups. Every original slot inventory, path
hash, response history, runtime score and known-work report was audited.
Each mode had 54 actual learned proposals and 18 guarded abstentions across
its six paths; the guard excluded target indices 0, 1 and 11. The source
retained native parent validation, strict snapshot decode/re-hash, exact
rollback/fallback behavior, unchanged solver settings and unchanged accepted
state authority.

The first audit at numerical source reported `all_pairs_exact=false` because
its `*-context.json` glob selected both twelve proposal and twelve guard
contexts, then required a count of twelve. Its original file SHA-256
`6b538d73e1a0ce6a5de50aad2bd67eb80d5cce9b0f09e17930704b7fff232b79`
is preserved. A separate read-only audit-only child commit
`c1b1b4009bf8c545e052a93830a5d712cff4421b` corrected the fixed roster
to 24 context and 13 step files per pair, without changing numerical code or
rerunning a path. It found **all six pairs byte-identical**, including the
preload step. The supplemental receipt hash is
`sha256:9af312e878bc38ccd0a04d42909d7f4f37755391ad45a67263c989fa6833a892`;
it binds the plan, original audit, and all twelve outcome and inventory file
hashes. [The three compact receipt copies](../../examples/research/rc_material_capture_cost/README.md)
are in Git. The original 220 MiB, 4,346-file numerical packet remains at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-capture-cost-packet-20260929-5187de5`;
the separate supplemental receipt is at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-capture-cost-supplement-20260929-c1b1b40.json`.

| Case | Repetition | Uncached proposal/secant | Cached proposal/secant | Cached/uncached capture | Cached/uncached proposal path |
| :--- | ---: | ---: | ---: | ---: | ---: |
| F | 0 | 0.995849 | 0.992123 | 1.024671 | 0.994643 |
| G | 0 | 1.030663 | 1.020868 | 1.024262 | 0.991133 |
| F | 1 | 0.983455 | 0.987140 | 1.033619 | 1.013027 |
| G | 1 | 1.003135 | 1.001583 | 1.018799 | 0.995234 |
| F | 2 | 0.975484 | 0.963263 | 0.996023 | 0.984353 |
| G | 2 | 0.998927 | 0.994586 | 1.043061 | 1.006162 |

F's three-run means were `0.9849292135` uncached and `0.9808418709`
cached; G's were `1.0109080399` and `1.0056790487`. The predeclared
equal-case means above average those two case means, not pooled wall times.
Across matched pairs the mean cached/uncached capture ratio was `1.0234058271`;
the mean complete proposal-path ratio was `0.9974251747`, with ratios on both
sides of one. The summed proposal-path wall time was `23.203566175 s`
uncached and `23.142802759 s` cached, while the separately measured secant
path sums also changed (`23.262542625 s` and `23.310375837 s`). These small,
variable whole-path differences do not establish a speedup. Capture, callbacks,
guard, solver attempts and recovery are nested within whole-path and slot
timings and must not be added together. Process startup and historical label,
fit and selection costs were not measured here; they are **unknown**, not zero.

An earlier plan-only packet at source `d8232a6aa8ed801f366d3ee2f01fb66d1e013b87`
launched one uncached F slot before a final accounting review found missing
aggregate timing containment. Its packet
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-capture-cost-packet-20260929-d8232a6`
is preserved with one completed slot and eleven missing/unknown slots. It was
excluded entirely from the twelve-slot matched comparison above.

F/G and A–E all descend from one authored public RC example template. Neither
distinct identifiers nor three timing repeats establish independent source
lineage. The result is a negative same-template cost diagnostic, not physical
accuracy evidence, a qualified learned policy, reserved evaluation, generalized
performance, or full AI lifecycle break-even.
