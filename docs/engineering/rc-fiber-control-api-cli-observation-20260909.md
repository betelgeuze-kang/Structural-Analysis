# RC control API and CLI source observation — 2026-09-09

At clean `7f78b4c833dc805bf54d53b7ac8e750914a51238`, the new canonical-model RC control API
and strict `run`/`verify` CLI complete the original 242-target path, prefix save,
fresh-process resume and standalone source verification. The full and resumed
accepted response histories and native restart bytes are exact. This verifies
local consistency of one authored synthetic small-displacement RC case; it does
not establish independent physics, public J1–J5 authority, general cyclic
validation, design approval, performance improvement or production readiness.

## Source and declared execution

The saved package contains 402 exact Git files from
the implementation revision. Source and input hashes were checked before and
after each process. The original L-frame model bytes have SHA256
`9f2a66f86fd5443574032ff4a55f3de09995094808f20c1b7f34ac403de6b59d`. The committed
[request example](../../examples/bounded_rc_fiber_direct_control_l_frame_cyclic.request.v1.json)
copies the previous fixed protocol's 242 target numbers without rounding or
retuning. DOF 7 controls N3 UY; two reversals, 40 Newton iterations, residual
tolerance `1e-10`, increment/control tolerances `1e-12`, and a `0.001 m` load-factor
coordinate scale remain explicit. The split is 122 accepted targets plus a
120-target suffix, with a cumulative budget of 255.

The [API/CLI contract](rc-fiber-displacement-control.md) includes runnable
commands. Every `run` performs the original analysis and mandatory fresh source
validation. Resume executes all 122 prefix solves before its 120 suffix solves
in both invocations. Standalone `verify` executes the full 242-target request
again. All four CLI processes exit 0 with artifact consistency and complete
physical-path flags. Seven API invocations perform 1,454 actual original
control-step calls on the same synthetic case. Replays do not add independent
physical specimens or material benchmarks.

| CLI operation | PID | API calls | Core calls | Known Newton/linear counts | Launch wall s | Lifetime peak RSS bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| full | 597784 | 2 | 484 | 1920 | 228.225130664 | 1246588928 |
| prefix | 599093 | 2 | 244 | 1154 | 120.751536891 | 748916736 |
| resume | 599456 | 2 | 484 | 1920 | 230.772129371 | 1226211328 |
| verify | 600027 | 1 | 242 | 960 | 109.640757203 | 997253120 |

Known Newton iterations and linear solves each total
**5954**; unknown-work attempts and failed control
steps are zero in this final observation. All
**1454** accepted transition recoveries
pass. Serial parent launch wall is **689.390239581 s**.
The transparent observer adds event, native step/checkpoint export and hash work;
it preserves original call arguments, return objects and exceptions. Its costs
are included. CLI analysis and verification intervals are separate in the
[machine summary](rc-fiber-control-api-cli-observation-20260909.summary.json); parsing/publication is outside those
intervals and inside the process total. Peak RSS is process-lifetime RSS, not
incremental solver allocation. These measurements are correctness costs with
instrumentation, not a speed comparison.

## Complete accepted history and saved-data audit

Each API response is freshly assembled from the actual previous parent,
original saved augmented Newton coordinates and solved load factor. The whole
assembly and original accepted material state must match. SI node/member/section
responses and all 84 material states
per epoch are retained across all 242 accepted epochs. Accepted steel plasticity
first occurs at epoch 15; terminal load
factor is `1.3828147147200147`, with native checkpoint hash
`sha256:6dabcfde2a29021849d606aa48cf4173e7da9b7e6c9ed4bfc640950295f073f4`. Terminal maxima are accumulated steel
plastic strain `0.009756536290480443`,
tensile damage `0.9999999999661977` and
compressive damage `0.13048993532825948`.
Those state maxima describe this calculation, not allowable engineering limits.

The separately authored saved-data audit passes 8,493 repeated field checks
with zero errors in 11.472902566 seconds. It checks complete response/native material
projection, all repeated step/checkpoint byte identities, original 242 checkpoint
bytes, prefix/resume histories, source/input bindings and actual work/event
accounting. It uses only saved data and the Python standard library; it runs no
Newton solve or constitutive reassembly. Repeated field checks are not independent
experiments, and hashes do not authenticate execution. The audit outcome,
complete-report identity and explicit limitations are included in the machine
summary; the complete report remains in the sealed raw bundle.

The earlier coarse and alternate-seed failures remain documented in
[the original control observation](rc-fiber-control-restart-observation-20260909.md).
They are not relabeled successful by this differently discretized path.

## Focused development verification

- API: 91 tests pass in 11.57 s. The first run retained 35 passes and one failed
  assertion in 13.27 s: it incorrectly treated a missing iteration count under a
  zero iteration budget as known zero. The corrected assertion preserves unknown
  solver work, with no production change or relaxed physical gate. The final
  run reused source-identical recorded fixtures, regenerated the small original
  path, and still executed explicit validator/restart cases. Actual core calls
  were 30 initially plus 11 on the corrected run; ordinary CI uses 32.
- Strict request/CLI: 99 pure/stub contracts pass in 1.88 s; a separate actual
  CLI case passes in 2.00 s, with three API invocations and six actual core calls.
- CI boundary/quality/workflow registration: 48 tests pass in 0.55 s.
- Focused Ruff/format/diff checks and independent API/request/CLI reviews pass.

These separate groups do not claim a prepared whole-repository suite pass.
The final frozen observation above is separate from those development calls.
Original failed logs and actual fixture artifacts are retained in its provenance.

## Retention and remaining work

Raw source, protocol, requests, driver, process outputs, actual native artifacts,
test provenance and saved-data audit are local under `/tmp/structural-rc-control-api-observation.ry94k4xt`. Their final
inventory covers **1000 files / 376225557 bytes**,
excluding the inventory itself. Inventory SHA256 is `0c2c16301c7901162e5502cedae3bce1f1f7459715f94efc796b207800722f8c`.
The sealed file set and every byte hash were rechecked after all writers stopped.
The raw bundle is retained on this host; GitHub contains this record, the concise
machine summary and reproducible request, not the full raw bundle.

The owner-authorized branch is published in
[draft PR #439](https://github.com/betelgeuze-kang/Structural-Analysis/pull/439),
linked to bounded implementation issue #438. Applicable exact-head hosted
checks and final cumulative review remain required. Durable job execution/resume,
Workbench review and verified study integration for this RC control profile are
still subsequent work. Broader M1–M5/P1–P3, independent/licensing/platform/operator
and release requirements remain open. Separate R2 integration branches are not
included here.

The first hosted implementation head (`7f78b4c83`) has two recorded failures:
[engine-v2-contract](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34287980265/job/102267864607)
reports a `bounded_planar_semantic_hash` golden mismatch (299 passes, one failure),
and [canonical-contract](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34287955683/job/102267788256)
reports a runtime SBOM exact-rebuild mismatch and stale downstream receipts.
The logs do not by themselves establish a physical regression or its exact cause.
These failures remain unresolved here; local RC checks do not replace them.
