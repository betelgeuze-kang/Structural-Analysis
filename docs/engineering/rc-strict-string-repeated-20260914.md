# Repeated full-data Workbench comparison of strict-string decoding

The [single profiled observation](rc-strict-string-profile-20260914.md) motivated
a repeated comparison without CPU profiling. Baseline source is
`5a0def37655a095c2bd25028b0be74142a6eebe2`; changed source is
`427b6c242` (the exact full revision is retained in the protocol).

## Frozen protocol and actual execution

Extract each frontend independently from Git and build it with the same installed
Vite/dependencies and Node 24.20.0. The current checkout is not reset or overwritten.
An optional `--frontend-directory` argument in the existing disposable HTTP fixture
selects the built version. An invalid build path is rejected before snapshot/service
creation; Ruff and this input-boundary check pass. Default fixture selection remains
available. This option affects the test fixture, not a production endpoint.

For each viewport, freeze the order baseline/changed, changed/baseline,
baseline/changed. Run 1440px and 390px widths, three observations per version per
viewport, twelve total. Every test gets a fresh browser context and its own real
HTTP server/snapshot. The same immutable 75-artifact / 525,181,454-byte candidate
result is used throughout. No CPU profiler or response interception is active.
OS file caches and shared browser-process state are not reset. A 390px headless
Chromium viewport is not a physical mobile device or mobile-network test.

All twelve tests pass in 4.3 minutes. Each validates the displayed comparison,
selection, original solver settings, model/result/checkpoint/verification/search
result downloads and horizontal bounds. Every response has the original length
and SHA256: 79 per run, 948 in total. No solver calls or fits occur. This tests one
existing result bundle repeatedly, not twelve independent physical structures.

## Results

| Viewport / interval | Baseline median, s | Changed median, s | Median paired changed/baseline |
| --- | ---: | ---: | ---: |
| 1440px navigation to verified panel | 16.3015 | 14.2798 | 0.876101 |
| 1440px through original-download checks | 18.7432 | 16.5317 | 0.892407 |
| 390px navigation to verified panel | 16.0977 | 15.1320 | 0.939601 |
| 390px through original-download checks | 18.1047 | 17.0154 | 0.939833 |

Changed verified-panel intervals are lower in all six adjacent pairs. Baseline /
changed ranges are 16.2686–16.4614 / 14.2789–14.2818 seconds at 1440px and
16.0793–16.1618 / 15.1081–15.1918 seconds at 390px. Exact values and sample
standard deviations are retained in the receipt. No statistical population
confidence or broad performance guarantee is inferred from three pairs.

The navigation interval includes page loading, authentication, transfer, worker
validation and test observation/polling. The longer interval additionally includes
automated UI interactions, downloads and test-side original-byte comparisons.
It is not human task completion time. It excludes server snapshot preparation,
frontend build time and screenshots taken afterwards. Server loading, wall/CPU
intervals and server-only peak RSS are separately retained; browser process memory
is not measured. These scoped intervals must not be summed with nested costs or
presented as total research lifecycle cost.

## Evidence and interpretation

The [receipt](rc-strict-string-repeated-20260914.json) binds both Git archives,
extracted sources/builds, frozen order, generated tests, original logs/timings,
screenshots, actual HTTP receipts and audit scripts. All 1,432 files /
297,084,052 bytes are reread and inventoried. Two explicitly listed node_modules
symlinks reference the shared dependency installation; dependency trees themselves
are not archived or made immutable. Node/Vite/Playwright versions are recorded.
Original artifact hashes are computed once per immutable path in the audit and
compared against every HTTP receipt, without additional numerical execution.

The repeated local evidence supports reduced consumer time for this particular
large result bundle while maintaining its checks. It does not establish faster
nonlinear solving, learned net benefit, other datasets, independent physics,
production/mobile-device latency or full roadmap completion. Those requirements
remain open; new-head hosted integration also remains required.
