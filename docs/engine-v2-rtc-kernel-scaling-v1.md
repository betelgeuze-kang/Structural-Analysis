# Engine v2 HIPRTC fused CSR kernel scaling gate v1

## Scope

`scripts/benchmark_engine_v2_rtc_kernel_scaling.py` measures only the fixed
package-owned HIPRTC kernel
`engine_v2_csr_residual_jvp_v1`. One thread owns one sorted CSR row and one
launch evaluates `R=Ku-F` and `Jv=Kv` in a single traversal.

This gate does not execute a structural solver. It excludes model import,
element/material assembly, `ExecutionPlan`, transfers, CPU oracle work,
linear/nonlinear solve, recovery, AI, and drawing optimization from every fit.
It has no CPU baseline, so it produces no speedup claim. A passing result is
only an initial scaling observation for this one fixed-degree fused kernel.

The JSON is an unsigned local measurement. Its canonical hash and internal
recalculation detect accidental or rehashed field inconsistencies, but cannot
authenticate raw timing provenance. Consequently every report has
`promotion_eligible=false`, `nonpromoting=true`, and cannot close a commercial
or release gate.

Each report binds the exact benchmark-script bytes, strict report-schema
bytes, Python implementation/version, and NumPy version in `harness_identity`.
The pre-write verifier re-hashes the current two files and rejects drift. This
improves reproducibility and tamper detection; it still does not substitute for
a signed build/provenance chain.

## Clean worker and native identity

The CLI always re-spawns itself before importing NumPy, Engine v2, HIPRTC, or
`libamdhip64`. The worker removes these variables from its environment:

- `HIP_LAUNCH_BLOCKING`
- `AMD_SERIALIZE_KERNEL`
- `AMD_SERIALIZE_COPY`
- conservative cross-runtime guard `CUDA_LAUNCH_BLOCKING`

The worker rejects any remaining serialization variable. It detects a real
`gfx*` agent with `rocm_agent_enumerator`, requires the exact native
`LoadedHipRuntime` and `HipRtcCsrKernel` owner types, and forbids fallback. No
real agent produces an explicit `unavailable` report and exit code 2.

The default cache/occupancy profile is deliberately device-specific:

- architecture: `gfx1030`
- device-name token: `6900 XT`
- cache reference: 128 MiB Infinity Cache
- compute units: 80
- kernel block size: 256

Another GPU may execute the measurements, but cannot receive `accepted` under
this profile. It becomes `inconclusive`; a separately reviewed hardware
profile is required rather than silently reusing RX 6900 XT constants.

## Sparse family and exact accounting

Every size uses a symmetric sorted tridiagonal CSR matrix in `<i4`/`<f8`:

```text
K[i,i]   =  2.50
K[i,i-1] = -0.25
K[i,i+1] = -0.25
Z        = 3N - 2
```

Eight allocations are made once per size: row pointer, column index, value,
state, load, direction, residual, and JVP. CSR/state/load/direction are uploaded
once. There is no allocation or transfer inside any event-timed interval.

The source-level accounting per launch is:

| Quantity | Exact formula |
| --- | ---: |
| FP64-equivalent work | `4Z + N` |
| source logical bytes | `28Z + 32N` |
| unique-read footprint | `12Z + 28N + 4` |
| resident/touched payload | `12Z + 44N + 4` |

`source_logical_bytes` is not a physical DRAM counter or achieved bandwidth.
Cache lines, transactions, coalescing, and reuse are not instrumented, so the
report fixes `physical_dram_bytes="not_instrumented"`.

The default fit points are predeclared before timing:

```text
4,194,305
6,291,456
8,388,608
12,582,912
16,777,220
```

They span exactly 4x. The first unique-read footprint is greater than twice the
128 MiB profile cache, and every point has at least eight blocks per reference
compute unit. Smaller rows are not substituted when memory is low. The largest
payload is about 1.25 GiB; preflight requires at least 2 GiB free and caps the
payload at 50% of observed free device memory. A failed preflight is
`unavailable`, not a resized fit.

## HIP event protocol

For each size, the predeclared measurement order alternates low/high sizes to
reduce monotonic thermal ordering bias. On the same non-blocking stream the
worker performs:

1. at least 20 non-timed warmup launches and a stream synchronization;
2. a small event-timed pilot;
3. adaptive K selection so the median K interval is at least 20 ms;
4. at least three K trials and three 2K trials;
5. seven main K batches used by the fit;
6. one same-allocation K repeat immediately after the main trials;
7. only then, two D2H copies and a chunked FP64 residual/JVP oracle.

Each interval is `start event -> K launches -> stop event -> stop-event sync ->
hipEventElapsedTime`. It measures steady-state same-stream dispatch plus kernel,
not a profiler-isolated kernel body. The K/2K per-launch medians must agree
within 3%, main-trial CV within 5%, and the within-size end repeat within 5%.
The report records pilot/calibration/stability/main/end raw data and the exact
total number of event-timed launches. The end-repeat drift is local to the same
allocation and size; it is not a second whole-sweep thermal repeat.

The post-timing oracle verifies finite values and full-vector residual/JVP
parity at absolute and relative-L2 tolerance `1e-10`. Those two D2H operations
are explicitly recorded outside the timed region and cannot affect a slope.

## Fit and decision

The worker fits log median per-launch milliseconds against log N using:

- ordinary least squares slope and R2;
- Theil-Sen median pairwise slope and diagnostic robust R2;
- deterministic, trial-stratified bootstrap of the Theil-Sen slope with a 95%
  interval (2,000 replicates by default).

`robust_r2` is diagnostic only. The initial accepted target requires all of:

- exact native profile, off-cache, occupancy, correctness, no-fallback, and
  timed-region purity;
- median event batch at least 20 ms;
- K/2K delta <= 3%, CV <= 5%, and within-size end drift <= 5%;
- OLS and Theil-Sen slopes both in `[0.85, 1.15]`;
- OLS R2 >= 0.98;
- bootstrap 95% slope interval wholly inside `[0.85, 1.15]`.

Correctness, fallback, or timed-purity violation is `rejected` with a distinct
contract reason. A clean, quality-qualified slope/R2 miss is `rejected`.
Cache/profile coverage, event duration, jitter, drift, or bootstrap-confidence
failure is `inconclusive`, even when a point slope looks favorable.

## Running

```bash
python3 scripts/benchmark_engine_v2_rtc_kernel_scaling.py \
  --out /tmp/engine_v2_rtc_kernel_scaling.json
```

Exit codes are 0 for `accepted`, 1 for `rejected`, `inconclusive`, or runtime
error, and 2 for invalid configuration or unavailable native hardware.

Focused hardware-independent verification:

```bash
python3 -m pytest -q tests/test_engine_v2_rtc_kernel_scaling_v1.py
```

## Current evidence boundary

On 2026-07-11 the final default gate
ran in a clean worker on the development
RX 6900 XT / `gfx1030` and returned `accepted`. The five median per-launch
times were:

| Rows | Median ms | Adaptive K | CV | K/2K delta | End drift |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 4,194,305 | 0.738956 | 54 | 0.000310 | 0.000319 | 0.000379 |
| 6,291,456 | 1.106482 | 19 | 0.001472 | 0.001581 | 0.000177 |
| 8,388,608 | 1.485136 | 14 | 0.001865 | 0.002098 | 0.000506 |
| 12,582,912 | 2.231998 | 9 | 0.001188 | 0.000444 | 0.000225 |
| 16,777,220 | 2.990096 | 7 | 0.000466 | 0.001894 | 0.000020 |

OLS slope was `1.0089193` with R2 `0.9999852`; Theil-Sen slope was
`1.0089559`, and its stratified-bootstrap 95% interval was
`[1.0084381, 1.0097521]`. All five post-timing residual/JVP checks and every
profile, off-cache, occupancy, 20 ms, K/2K, CV, drift, no-fallback, and
timed-purity condition passed. This remains unsigned single-workstation
kernel-only evidence and is not a product or solver benchmark. The unsigned
report hash was
`sha256:dddf5f60b1f847acb7223bde38a0f7c2b5a5062089028e8c2401531136d707c3`.
It binds benchmark-script hash
`sha256:697d9ce877a3a56963a8be286cb6fc3d8d8dba6da9c0b7c411a0784b103825eb`
and report-schema hash
`sha256:c668ec599b01e1ce84cfc746eb0d3cc6506da5b4289fb5891f7010a7c30622fa`;
it is an integrity checksum, not a signature or promotion credential.
The report is stored at
`validation/observations/engine_v2/rtc_kernel_scaling_gfx1030_unsigned_v1.json`.

An exploratory clean-event run on the development RX 6900 XT measured rows
2,097,152 / 3,145,728 / 4,194,304 / 6,291,456 / 8,388,608 at median 0.32957 /
0.55865 / 0.74093 / 1.12786 / 1.50175 ms, with log-log slope 1.08025 and R2
0.99650. That family crosses cache regimes and predates this final gate, so it
is disclosed as a diagnostic only and cannot yield `accepted`.

Even an accepted final report would demonstrate neither end-to-end `O(N)` nor
solver complexity. A separate sparse-only CPU plan now exists, but the roadmap
still requires measured compile/peak-memory evidence, device element assembly,
device-resident Krylov/preconditioning/Newton, nonlinear constitutive assembly,
multi-architecture V&V, signed provenance, and whole-product benchmarks.
