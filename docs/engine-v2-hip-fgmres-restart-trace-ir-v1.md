# Engine v2 HIP FGMRES diagnostic restart TraceIR v1

- Milestone: v0.2.53 unpublished candidate
- 기준일: 2026-07-17
- 상태: implemented, contract-only, unsigned, process-local, non-persistent, non-promoting
- 대상: general-history parity v2의 ResultIR와 분리된 restart 진단 trace

## 1. 목적

v0.2.52는 restart별 solution/true-residual vector와 다섯 scalar metric의 CPU/HIP
parity를 검증했지만, 그 receipt자체는 해석 결과 IR이 아니다. 본 단계는
검증된 general-history receipt를 순서화된 진단 TraceIR로 투영하면서 다음
경계를 고정한다.

1. TraceIR은 수렴 경로 관찰용이며 final solution/ResultIR이 아니다.
2. StateIR commit, reaction, member force, energy, code check, design 및 optimization 권한을 발행하지 않는다.
3. 중간 vector는 새 wire에 복제하지 않고 CPU reference/HIP candidate SHA-256로만 참조한다.
4. 수치 vector가 필요한 process-local consumer는 attached result의 기존 v0.2.52 source payload를 사용한다.

## 2. Wire 계약

Trace receipt은 source parity identity와 전체 binding chain을 유지한다.

- source parity ID/receipt hash
- ExecutionPlan/operator/policy hash
- CPU checkpoint/base result hash
- completion export v2 context/receipt/payload hash
- retained completion v1, history export v1, terminal observation hash
- global context, history ABI/plan, recurrence plan/kernel identity
- architecture와 device ordinal

각 trace row는 source restart row의 canonical hash, restart/slot/column, iteration 구간,
Arnoldi/reorthogonalization count, termination hint, flags를 보존한다. Solution과
true residual은 value count, CPU/HIP vector hash, 오차 지표, fixed tolerance gate를
참조한다. 아래 다섯 scalar envelope는 source의 outward-rounding 필드를 그대로
투영한다.

- true residual L2
- true residual L∞
- scaled true residual
- estimated residual L2
- solution update L2

Solution vector의 fixed componentwise gate는 항상 true여야 한다. True-residual은
fixed gate가 false여도 v0.2.52의 componentwise CSR roundoff receipt가 검증한 범위에서
진단값으로 보존한다. Trace에서 residual fixed gate를 solution authority로
승격하지 않는다.

## 3. Detached·attached 경계

`build_hip_fgmres_restart_trace_ir_receipt_v1` 결과는 strict Draft 2020-12 schema와
canonical hash를 갖는 detached descriptor이다. Source receipt와 결박된 해시 commitment이지
standalone provenance authenticity가 아니다.

`build_hip_fgmres_restart_trace_ir_v1` 결과는 exact general-history result를 같이 보유한다.
Attached validator는 source result를 다시 검증하고 deterministic projection과 exact equality를
요구한다. 이는 process-local Python object binding이며 hostile same-process 변조 저항,
서명, 영속성 또는 cross-host authority를 의미하지 않는다.

## 4. 비용과 계측 경계

Restart 수를 `R`이라 하면 detached wire의 row projection은 `O(R)`이다.

- embedded numeric vector bytes: `0`
- ResultIR arrays: `0`
- state commit: `0`
- additional device operation/D2H/solve/export/fallback: 모두 `0`
- vector reference: `2R`
- scalar envelope reference: `5R`

기존 history payload의 `O(RF)` host/device storage와 completion D2H `5`회를 삭제하거나
숨기지 않는다. Trace projection의 `O(R)`은 전체 FE 해석 `O(N)`, iteration-count
scaling, memory slope 또는 wall-clock speedup 증거가 아니다.

## 5. 검증

- pure detached projection/adversarial contract: `8 passed`
- public API/schema resource: `2 passed`
- general-history public compatibility: `5 passed`
- capability matrix: `17 passed`
- combined focused contract: `32 passed`
- adjacent CPU checkpoint history / HIP history plan / RTC: `5 / 11 / 5 passed`
- isolated wheel regressions: high-load aggregate public `2 passed`, ResultIR v3 package `1 passed`
- hardware harness: `1 test collected`
- public symbols: Engine v2 `1085`, assembly backend `912`, solvers `47`, 각각 unique
- current source/schema/hardware-harness aggregate: `sha256:2661f3745b432bba1fd21aea0bf3e8bf0d8e12e5122c92c587dd49221efdeda1`

현 namespace에 `/dev/kfd`와 `/dev/dri`가 없으므로 TraceIR이 포함된 current-source
required `gfx1030` gate는 수치 경로 전에 `No real gfx agent was detected.`로
fail-closed했다. v0.2.52의 이전 hardware 관찰은
신규 TraceIR 실행 증거로 재분류하지 않는다.

## 6. Claim boundary와 다음 순서

이 milestone은 다음을 증명하지 않는다.

- raw checkpoint vector payload를 독립 artifact에 embed한다는 claim
- final solution, ResultIR, StateIR commit, reaction/member-force/energy recovery
- external `gfx1100` 및 two-architecture parity
- persistent/cross-process/signed/standalone provenance
- process-wide iteration host-copy-zero
- end-to-end `O(N)`, memory scaling, performance 또는 speedup
- nonlinear/dynamic/modal/buckling/shell/solid/contact
- promotion eligibility 또는 commercial readiness

다음 순서는 external `gfx1100` signed/persistent replay와 동일 trace identity 결박, 그 다음
GPU-native recovery/ResultIR의 별도 권한 연결이다. TraceIR을 ResultIR로 승격하는
우회는 허용하지 않는다.
