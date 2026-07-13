# Engine v2 HIPRTC FGMRES recurrence substrate v1

- 상태: 구현된 7-symbol 저수준 HIPRTC substrate, unsigned·non-promoting
- 범위: fixed-source module/launch/solve-record ABI와 completion-fenced module lifetime
- 수치 기준: [CPU fixed-restart FGMRES reference v1](engine-v2-cpu-fgmres-reference-v1.md)
- allocation 기준: [HIP fixed-restart FGMRES plan v1](engine-v2-hip-fgmres-plan-v1.md)
- 상위 기준: [Structural Solver Engine v2 마스터 로드맵](structural-solver-engine-v2-master-roadmap.md)

이 v1은 **FGMRES solver가 아니다**. 향후 live solver child가 사용할 package-owned HIPRTC module과 solve-record ABI의 첫 수직 slice다. 현재 코드는 장치 배열을 할당하지 않고, solver context·Arnoldi recurrence·수렴 solution receipt를 발행하지 않는다.

## 고정 7-symbol module

`engine_v2_fgmres_v1.hip.cpp`는 다음 심볼만 제공한다.

| 심볼 역할 | 수행 범위 |
|---|---|
| `record_initialize` | header/restart 영역 zero, tolerance·RHS norm·scheduled count 초기화 |
| `csr_spmv` | active-mask를 따르는 reduced CSR FP64 SpMV |
| `residual` | `r=b-Ax` |
| `copy_scale` | host-by-value scalar를 사용한 vector copy/scale |
| `apply_jacobi` | finite-positive inverse diagonal의 elementwise 적용 |
| `control_terminal` | 외부 device scalar pointer의 L2/L∞를 사용한 initial/final dual gate |
| `record_restart` | host-by-value restart metric·hint·flag 기록 |

모든 vector kernel은 record의 recurrence ABI와 `active`를 열어 본 뒤 실행한다. CSR 구조, nonfinite input, arithmetic overflow, invalid control, record ABI, Jacobi 오류는 고정 device error bit와 terminal failure로 남긴다. CPU/SciPy fallback, allocation, memcpy, device-wide synchronize는 kernel source에 없다.

## Solve-record ABI 공유

Plan과 RTC identity는 `hip_fgmres_solve_record_abi_payload_v1()`의 같은 canonical payload를 hash한다.

```text
byte order       = little-endian
header           = 192 bytes = 16*i32 + 16*f64
restart record   = 72 bytes  = 7*i32 + 4-byte pad + 5*f64
total extent     = 192 + 72*R
```

공유 payload에는 모든 field offset만이 아니라 terminal status, termination reason, restart hint, restart flag bit 매핑도 포함된다. RTC identity는 이 layout hash와 recurrence ABI version, 7개 symbol, block size, fixed source hash, gfx target/options, HIPRTC/runtime library identity, code-object hash를 함께 결박한다.

별도 kernel-interface hash는 device error bit, control mode, symbol별 argument type/source, grid/block rule와 solve-record layout hash를 결박한다. HIP source에는 이 interface hash marker가 있고 `_fixed_source()`가 컴파일 전 marker, 전체 header/restart offset·status/reason/hint/flag/error/control integer 상수, 7개 C symbol의 const/mutable pointer를 포함한 exact argument declaration을 모두 canonical payload와 대조한다. 따라서 plan/host identity와 수동 kernel 상수·signature가 독립적으로 drift할 수 없다. ABI mismatch는 더 이상 silent no-op이 아니며 `record_abi` device error로 terminal fail한다.

Header offset 60은 fixed `restart_dimension`을 보관한다. Restart writer는 `restart_index=previous+1`, `start_iteration=previous_end`, `step<=M`, `reorth<=step`, normal restart의 예정 step 수, true-residual replay, L2/L∞ gate bit·hint 일치와 scaled residual 재계산을 장치에서 검사하여 slot overwrite·skip·후퇴를 거부한다. Max-iteration control도 `effective_iterations==scheduled_iterations`일 때만 허용한다. 입력 nonfinite, 연산 overflow, Jacobi invalid 원인은 서로 다른 error bit로 분류한다.

CPU oracle과 같이 restart 경계의 dual gate 통과는 hint `restart_completed`를 유지하며 termination code `converged_restart_true_residual`로 전이한다. Inner candidate 통과의 `converged_true_residual`과 happy breakdown code는 별도로 유지한다.

`record_initialize` 및 `control_terminal`이 받는 norm은 device pointer이지만, 이 substrate에는 L2/L∞ reduction producer가 없다. `record_restart`의 metric과 flag는 host-by-value이므로 현재 ABI를 device-resident recurrence 증거로 사용할 수 없다.

## Module lifetime

런처는 동일 stream으로 제출된 work를 pending으로 기록한다. 호출자가 해당 stream의 completion fence를 관찰한 뒤 `acknowledge_stream_completion()`을 호출하기 전에는 module unload를 거부한다. Load 후 symbol 회수·identity 생성이 실패한 경우 module을 회수하고, unload 실패는 owner를 버리지 않아 재시도할 수 있다.

향후 context의 소유권은 다음 계층을 따라야 한다.

```text
assembly -> resident CSR -> free-space -> Krylov primitives -> FGMRES child
```

Krylov primitive context에는 exact source apply·execution/free-space plan·view hash·pointer·runtime/loaded-runtime·architecture·stream identity를 snapshot하는 exclusive FGMRES solver-child lease가 추가되었다. 객체 binding은 identity로, scalar/hash binding은 exact type/value로 매 작업 전 재검사하고 drift를 전체 owner chain에 poison한 뒤에도 exact token cleanup은 허용한다. 이 v1 문서의 범위는 lease substrate뿐이다. 후속 [live checkpoint resource context v1](engine-v2-hip-fgmres-live-checkpoint-context-v1.md)은 parent3+owned8 allocation/module lifetime을 별도 구현했지만 아직 수치 producer나 solver schedule을 실행하지 않는다.

## 검증된 경계

Focused test는 다음을 검증한다.

- fixed source와 7개 symbol의 정확한 회수
- shared solve-record payload, layout/code/flag hash, identity forgery 거부
- 모든 launch wrapper의 scalar/pointer ABI와 grid/block geometry
- invalid extent/control/pointer·missing symbol·launch/unload failure의 fail-closed 처리
- pending-stream acknowledgement 전 module unload 금지
- 실제 `libhiprtc`를 사용한 `gfx1030` code-object compile와 `llvm-nm` 7-symbol 확인

실제 HIPRTC compile은 통과했지만 physical GPU에서 recurrence를 실행하거나 CPU↔HIP 수치 parity를 측정한 것은 아니다.

## 완전한 FGMRES로 가기 위한 다음 순서

1. deterministic L2 LASSQ와 L∞ abs-max reduction을 solve-record/control scalar에 연결
2. base pointer+logical index 방식의 device-scalar scale/AXPY와 V/Z/H indexed operation 추가
3. device-controlled MGS/DGKS, incremental Givens, scale-relative backsolve 구현
4. `x_trial=x+Zy`, true residual replay, candidate commit/reject, stagnation/divergence/breakdown control 구현
5. **후속 v0.2.19 resource-only 완료**: exact source apply·primitive child lease, parent3+owned8와 RTC v2 module을 소유하는 live context 구현; content producer/solver는 미완료
6. raw iteration H2D/D2H/allocation/sync/fallback 0 receipt와 compact completion/export 경계 검증
7. CPU oracle parity, happy/unhappy breakdown, `M=2,I=5 → 2+2+1`, false-convergence 픽스처, native hardware gate 통과

위 항목 전에는 `fgmres_solver_ready`, `solution_ready`, `iteration_host_copy_zero_proven`, `native_recurrence_parity`, O(N), speedup, ResultIR 통합, 상용 준비 주장을 모두 금지한다.
