# Engine v2 HIP FGMRES checkpoint history / general parity v2

- Milestone: v0.2.52 unpublished candidate
- 기준일: 2026-07-17
- 상태: implemented, contract-only, unsigned, process-local, non-persistent, non-promoting
- 대상: frozen recurrence-v2/solve-record-v2 ABI에 additive한 per-restart solution/true-residual history

## 1. 목적

v0.2.50과 v0.2.51의 model-case parity는 completion에 남은 단일 terminal vector를 사용했다. 기존 solve record의 restart row에는 scalar metric만 있어서, 중간 restart의 solution과 true residual을 바이트 단위로 다시 검증할 수 없었다. v0.2.52는 기존 recurrence-v2와 solve-record-v2 wire ABI를 변경하지 않고 다음 additive 계약을 추가한다.

1. 각 restart에서 확정된 `solution_x`와 `true_residual`을 담는 두 companion device blob
2. 기존 3-buffer completion export v1과 두 history blob을 구성하는 5-buffer completion export v2
3. 결정적 CPU checkpoint vector reference v2
4. solve-record row, captured vector, sparse residual roundoff, GPU-tree scalar metric을 restart별로 교차 결속하는 general history parity v2

이 단계는 중간 restart 수치 이력을 검증 가능하게 만드는 것이지 ResultIR 발행, 성능 우위, 상용 승격을 의미하지 않는다.

## 2. Companion history ABI

두 blob은 독립 allocation이지만 동일 layout을 사용한다.

- role: `checkpoint_solution_history`, `checkpoint_true_residual_history`
- byte order: little-endian
- header: `64 bytes`, `16 * i32`
- restart row: slot당 `32 bytes`, `8 * i32`
- vector payload: row-major `<f8[R,F]`
- blob extent: `64 + 32R + 8RF`
- owned device extent: `2 * (64 + 32R + 8RF)`
- fixed launch block: 1 block, 256 threads

초기화 kernel은 두 blob을 0으로 지운 뒤 header를 publish한다. Capture kernel은 solve-record row가 해당 `(restart, column, end_iteration)`을 publish한 경우에만 solution/residual FP64 bit pattern을 복사한다. 모든 lane의 vector copy 이후 `threadfence`를 수행하고 metadata와 `captured=1`을 마지막에 publish한다. Detached decoder는 partial row, dirty unpublished row, 두 role의 metadata 불일치, device error bit, capture-count 불일치를 fail-closed한다.

`F=24`, `R=3`인 현재 multi-restart fixture의 blob은 role당 `736 bytes`, 합계 `1,472 bytes`이다. 해당 plan의 ABI hash는 `sha256:e24ec69cb326f777e47a40f69d39aca6bdce9ba669d32ffd0b0ed541e8132225`이다.

## 3. Live context와 5-buffer completion

History context는 global recurrence suffix 시작 전 optional child lease를 독점한다.

- 부모의 exact runtime/device/stream과 source allocation capability 3개를 결속한다.
- allocation-lineage owner가 두 `u8` history blob을 mint하고 source/destination non-overlap을 검증한다.
- initialization 1회 후 prefix restart-1/column-0 capture를 제출한다.
- 부모가 각 checkpoint finalizer를 제출한 직후 companion capture를 같은 stream에 제출한다.
- history capture 실패는 history child만 poison하고 frozen base solve를 중단하지 않는다.
- global fence 이후만 두 blocking D2H bulk copy를 허용한다.

Completion export v2의 순서와 dtype은 다음과 같다.

| index | role | dtype | owner |
| ---: | --- | --- | --- |
| 0 | `solution_x` | `<f8` | retained completion export v1 |
| 1 | `true_residual` | `<f8` | retained completion export v1 |
| 2 | `solve_record` | `|u1` | retained completion export v1 |
| 3 | `checkpoint_solution_history` | `|u1` | history context v1 |
| 4 | `checkpoint_true_residual_history` | `|u1` | history context v1 |

Composite layer 자체의 allocation, H2D, kernel launch, explicit sync, numerical branch, fallback은 모두 0이다. Nested owner의 blocking D2H만 `3 + 2 = 5`회로 계수한다. 정상 `context_closed`는 실패 상태가 아니므로 reason이 null인 독립 lifecycle receipt로 검증한다.

## 4. CPU reference와 general history parity

CPU FGMRES v1의 public result와 기존 core 기본 경로는 변경하지 않았다. Optional checkpoint sink가 각 accepted restart의 exact solution과 sparse `b-Ax`를 immutable `<f8` vector pair로 보존한다. Validator는 다음을 전수 재생한다.

- restart 순서와 base history row identity
- solution/residual shape, dtype, immutable backing, hash
- CSR true-residual exact replay
- residual L2/L∞/scaled-L∞와 solution-update L2
- checkpoint bundle/result canonical hash
- 동일 plan/policy의 deterministic full replay

General history parity v2는 populated restart마다 다음을 검증한다.

1. CPU history row, solve-record row, capture metadata의 restart/iteration/column/flag identity
2. checkpoint solution의 `atol=1e-12`, `rtol=1e-8` componentwise gate
3. CPU/HIP true residual vector 차이의 componentwise FP64 CSR roundoff receipt
4. HIP residual에서 GPU-tree L2/L∞/scaled-L∞ exact replay
5. 이전 checkpoint대비 solution-update GPU-tree L2 exact replay
6. true-residual metric, estimated-residual, solution-update의 outward total envelope

Estimated residual envelope는 estimator와 true residual 간 gap을 CPU/HIP 각각 명시적으로 더한 보수적 decomposition이다. 예측 오차나 formal proof를 주장하지 않는다. Parity layer 자체의 D2H, allocation, H2D, kernel, sync, fallback은 모두 0이다.

## 5. 복잡도 경계

`M`을 restart dimension, `R=ceil(I/M)`을 restart slot 수, `F`를 free DOF라 하면:

- history storage: `O(RF)`
- fixed capture submissions: `R*M`
- active vector copies: restart당 solution/residual 한 쌍, 합계 `O(RF)`
- detached validation/parity: sparse residual replay를 포함해 `O(R(nnz+F))`

고정된 bounded `M`/`I`에서 단일 FE 문제 크기 `N`에 대한 선형 스캔으로 취급할 수 있지만, iteration/restart 수가 문제 크기와 함께 증가하는 일반 경우의 end-to-end `O(N)` 증거는 아니다. AMG/DD, iteration-count scaling, peak-memory slope, wall-clock speedup은 별도 benchmark gate가 필요하다.

## 6. 검증 결과

- plan/blob, HIPRTC, CPU checkpoint, public API focused: `24 passed in 110.20s`
- 기존 global recurrence/completion v1/model-case v2/model-family v2 인접 회귀: `100 passed in 1632.11s`
- JSON Schema Draft 2020-12: plan, CPU history, live context, completion v2, parity v2 5개 schema 통과
- Ruff, formatting check, `py_compile`, public export uniqueness 통과
- public symbols: Engine v2 `1066`, assembly backend `893`, solvers `47`
- capability matrix: `16 passed in 0.24s`
- current wheel exact-resource / isolated replay: `2 passed in 38.19s`
- ResultIR v3 adjacent public/wheel regression: `6 passed in 12.25s`

실제 local RX 6900 XT `gfx1030` required gate의 fixture는 `recurrence_later_restart_partial_final_cycle` (`F=24`, `M=2`, `I=5`, `R=3`)이다.

- populated restart rows: 3, end iterations `(2, 4, 5)`
- history capture launches: `6/6`, initialization을 포함한 acknowledged module launches `7`
- history owned bytes: `1,472`
- base/history completion D2H: `3 + 2 = 5`
- composite additional device/D2H/sync/fallback: `0`
- solution row maximum absolute errors: `0`, `2.71e-20`, `2.71e-20`
- maximum residual roundoff ratios: `0`, `0.02252`, `0.03053`
- final current-source required hardware test: `1 passed in 100.30s`
- final wall clock / peak RSS: `101.00s` / `366,808 KiB`
- run-scoped parity id: `sha256:fb2402824f20e4ded1b93780d0c976aedf5a5aeb4c197a96f35da3468cb4b482`
- run-scoped parity receipt: `sha256:61c46985cfd1d22963738f4a957692c1117b2c00f11981d21150602f554ccc56`
- run-scoped completion receipt: `sha256:702e9c6b41c5fd72408e9ab31a3f9143a05720a5eeb12f1897b783b6879abfcb`
- 실행 전후 source/schema/hardware-harness aggregate: `sha256:a9749e6a3ca23148a9074b5b3d7e3a6a36435c8bf2c8178ff308e87288a47dac`

위 identity는 allocation lineage를 포함한 unsigned local process observation이므로 다른 실행에서 receipt hash가 달라질 수 있고 영속 external evidence가 아니다. Final required gate는 실행 전후 source aggregate 동일성과 history/composite `context_closed`, `reason=null` schema validation을 통과했다.

## 7. Claim boundary와 다음 단계

이 milestone이 증명하지 않는 항목:

- external `gfx1100` 및 two-architecture parity
- process-wide ROCm activity completeness와 iteration host-copy-zero
- persistent/cross-process/signed provenance, reproducible release artifact
- formal machine proof
- solution-ready 또는 ResultIR-ready issuance
- end-to-end `O(N)`, peak-memory near-linear gate, wall-clock speedup
- AMG/DD/deflation production preconditioner
- GPU-native reaction/member-force/energy recovery
- nonlinear, dynamic, modal, buckling, shell, solid, contact
- promotion eligibility 또는 commercial readiness

다음 순서는 다음과 같다.

1. General-history receipt의 ResultIR-분리 진단 trace는 v0.2.53 [diagnostic restart TraceIR v1](engine-v2-hip-fgmres-restart-trace-ir-v1.md)에서 additive contract로 연결했고 current-source local `gfx1030` gate를 통과했다. Raw vector는 새 wire에 embed하지 않고 source hash로만 참조한다.
2. `gfx1100` external runner에서 동일 fixture/schema/kernel/trace identity를 서명·영속 receipt로 재생한다.
3. AMG/DD 전처리와 fixed-rank orthogonal coarse correction을 추가하고 iteration/memory/time scaling을 별도 계측한다.
4. Device recovery와 ResultIR를 별도 권한으로 연결하되 CPU sparse physics replay와 fail-closed fallback telemetry를 보존한다.
