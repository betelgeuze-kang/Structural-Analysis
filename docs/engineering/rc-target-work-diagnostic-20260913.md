# Where learned warm-start work increases — 2026-09-13

At diagnostic source `eaadd228969b41bcb0fecfe32f6be4414ff93b6f`, the original
12-fold native-reuse runtime campaign was decomposed by prescribed target index.
This is a post-run diagnostic of stored execution counters, with **zero new solver
calls or fits**. It does not turn different accepted trajectories into causal
same-parent training labels or validate a prospective switching policy.

The new `rc_control_target_work_diagnostic.py` requires a pinned self-hashed
complete comparison, full-history agreement, aligned targets/decisions and known
integer invocation work. It includes target fallback/recovery invocations rather
than dropping unsuccessful proposals. It separates the first target, direction
reversal, new maximum absolute prescribed displacement, and remaining targets
within the preceding absolute-displacement envelope. These are prescribed-history
labels, not claims about yielding, damage or material unloading state.

The caller independently binds decision records to the original experiment; a
decision digest alone does not authenticate their provenance. Original runtime
documents and decisions were checked against the sealed source packet inventory.
No current solver acceptance tolerance or policy default changed.

## Observed concentration

The original campaign has four authored cases, three repeats each, and 2,904
aligned target pairs. Only `train-b` actually proposed learned seeds. The other
three cases retain identical secant/proposal counters on their abstention paths.

| Train-b prescribed segment | Targets across three repeats | Fewer / equal / more Newton targets | Net extra Newton iterations |
| --- | ---: | ---: | ---: |
| New absolute envelope | 147 | 30 / 78 / 39 | 12 |
| Direction reversal | 6 | 0 / 3 / 3 | 3 |
| Within preceding envelope | 570 | 66 / 222 / 282 | **276** |

The three initial reference-abstention targets add no difference. Thus 276 of
291 net additional iterations (**94.8%**) occur within the previous absolute
displacement envelope. Across the 723 actual proposed targets, 96 use fewer
iterations, 303 the same and 324 more. The target-by-target counter deltas are
identical across the three train-b repeats; these repetitions are not independent
physical cases.

Recorded native assembly dispatch phases provide another useful distinction:

| Train-b assembly phase | Secant | Learned proposal |
| --- | ---: | ---: |
| Primary iteration | 726 | 726 |
| Line search | 708 | **1,068** |
| Terminal refinement | 1,440 | 1,437 |
| Final observation | 726 | 726 |

The 360 additional line-search dispatches are distinct from the 291 additional
reported Newton iterations. Dispatch phases and inclusive solver counters measure
different work and must not be equated. The evidence points toward line-search
acceptance cost during within-envelope segments as a specific next experiment.
It does not prove that a reversal-only switch, a residual-based seed model or any
post-hoc hybrid would save time when replayed through a changed accepted path.

## Interpretation and next experiment

The full-path time disadvantage remains the original measured result. This
diagnostic does not recompute or improve its runtime ratio. It narrows the next
test: freeze a candidate rule on training-only evidence, compare secant and the
rule through complete fresh paths, and include feature/residual evaluation,
line-search, recovery and training costs. A coordinate-error improvement alone
does not answer whether the proposed seed is easier for the solver to accept.

Same target index does not mean same parent state. Only 2,184 of all 2,904 pairs
have equal recorded parent hashes, predominantly abstention cases; a matching hash
also does not establish the same secant coordinate prefix. The pre-existing
`rc_control_step_work.py` API and its stricter prefix checks are preserved byte for
byte. The new diagnostic lives in a separate module; an intermediate naming
collision was repaired before publication and its preliminary observation is not
the final evidence packet.

## Verification and provenance

Ruff and focused mypy passed. **55 focused tests passed**, including the original
step-work API, training diagnostics and workflow contract. New controlled tests
cover segment grouping, included fallback work and refusal of unknown counters,
Boolean counters/indices, partial paths, history mismatch, misaligned decisions
and an incorrect report pin. They are accounting tests, not physical simulations.

The final packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-target-work-u51q0u7h`:
14 files, 1,100,709 bytes, inventory SHA-256
`e7bc0400593e4584f414eed50d24caa5759835abf5f9c740679db6e926ccd49a`.
It records 25 inventory-checked original input files, all 12 diagnostics, the
observer and aggregate. See the [machine summary](rc-target-work-diagnostic-20260913.summary.json).
The original numerical source is `9374eb140725a67edfd7cca3c04a4febe3f3fbeb`.

Current-head hosted checks were inspected before this work: Repository Python
Tests run `34712654108` had no job rows while pending; Issue State Current's
offline contract job succeeded and its main-only live job was skipped. Neither
closes hosted full-suite or live exact-main requirements. Independent validation,
authenticated project/history transfer, learned net benefit and the broader
material/3D roadmap remain open.
