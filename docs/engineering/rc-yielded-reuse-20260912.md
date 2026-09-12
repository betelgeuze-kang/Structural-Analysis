# Assembly reuse through committed RC yield and unloading

Retained arithmetic preserves **128 paired native step files byte for byte**,
while reducing actual Newton assembly dispatches from **1,576 to 1,156** (420
fewer, 26.65%). Whole-benchmark wall time is **20.31% lower** in two order-balanced
repetitions. These are local observations on one authored L-frame and a bounded
yield/unload prefix, not a general speed guarantee or an AI gain. Default solver
behavior remains unchanged.

The binary64 baseline failed its existing full-history comparison **before any
reuse execution**. Its failure is retained and receives no speed ratio. This
result qualifies neither binary64 reuse nor a combined arithmetic result.

## Predeclared experiment

`--case yielded-prefix` uses the exact 16 floating-point targets already declared
by `YIELDED_RC_TARGETS_M` in the displacement-control regression. It reaches
-0.006 m and unloads to -0.0056 m. No target search or interpolation is performed.
Control DOF is 7, maximum Newton iterations 40, terminal polishing enabled, and
no constant preload is added. This is one unloading step, not a full cyclic
material test. The retained profile uses the existing arithmetic configuration.

Base revision `3ed360eca013570684bc139357e6d75604c20ed3` plus the source-hashed
runner changes. Each benchmark executes reference, secant, deterministic-secant
proposal, and fresh-reference paths. No learning occurs. The one-use wrapper
and unchanged verification rules follow the [initial experiment](rc-line-search-reuse-20260912.md).

| Execution | Step executions | Full-history status | Reuse/baseline wall ratio |
| --- | ---: | --- | ---: |
| Binary64 baseline only | 64 | Reference repeat exact; secant and proposal fail | null |
| Retained, baseline first | 128 | All pass; 64 paired steps exact | 0.798002 |
| Retained, reuse first | 128 | All pass; 64 paired steps exact | 0.795875 |

Retained runs contain 256 step executions across 16 complete paths. All 12
full-history comparisons pass. Each baseline benchmark dispatches 788 assemblies;
reuse dispatches 578 and records 210 separate hits. Final, terminal, and blocked
observations remain fresh.

Every retained path first has positive **committed** accumulated steel plastic
strain at zero-based step 14, approximately `7.86764100274818e-6`, and retains
positive memory after unloading. This is read from accepted checkpoint material
states, not inferred from requested displacement or a trial counter. It does
not demonstrate large-cycle degradation, shear or independent physical accuracy.

## Failed baseline and continuation

Binary64 secant and proposal each have 46 member-end-force, 16 section-result,
and 5 support-reaction mismatches at unchanged tolerances. Maximum mixed-field
absolute difference is `6.810296326875687e-9`; different fields have different
units, so this is not a single physical error measure. All four paths completed
and work was accounted for. Fresh reference is exact. The runner stopped on
comparison failure before reuse ran.

Retained arithmetic was already in the original schedule. After the binary64
stop, `--arithmetic retained` executes that remaining condition in a separate
output directory. There is no binary64 retry or tolerance relaxation. Both logs,
all raw reports, a post-failure working diff and final source snapshots are kept.
The first invocation predates the arithmetic-selection CLI extension. Its exact
launch-source bytes were not separately captured; the final source hash attests
the retained invocation, not the earlier failed invocation.

## Verification and limitations

**19 focused tests pass**, including cache boundaries, strict repetition and
arithmetic selection, and exact agreement with the regression targets. The
runner now requires every full-history comparison to pass before issuing a
successful paired summary. Ruff and diff checks pass.

```bash
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 scripts/diagnose_rc_control_line_search_reuse.py \
  /absolute/new/output-directory --repetitions 2 \
  --case yielded-prefix --arithmetic retained
```

Packet: 1,962 files / 97,800,368 bytes. Its adjacent inventory was reread and
verified, SHA256 `ae72c2955e034411e03780088ffee5c506acae27a41fbec4f8f944078a195111`.
Counts, timings, committed material observations, failures and exact paths are
in [the summary](rc-yielded-reuse-20260912.summary.json).

Time includes serialization, verification, recording and cache work. Aggregate
ratio `0.7969386146` is a ratio of summed times on a non-isolated host. Two
repetitions do not establish uncertainty bounds or generalization. The next
implementation step is explicitly scoped reuse without a process-global patch,
with failure and rollback verification. AI still needs separate net-benefit
evaluation against that deterministic baseline. External-reference CI,
independent physics and release acceptance remain open.
