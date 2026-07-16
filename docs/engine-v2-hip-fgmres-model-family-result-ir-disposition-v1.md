# Engine v2 HIP FGMRES Model-Family ResultIR Disposition v1

## 판정

`v0.2.44`는 exact package `gfx1030` 10-slot의 결과 상태를 정직하게 닫는
contract-only 후보 milestone이다. 현재 fixture registry는 10개 모두를 수렴시키는
성공 예제 집합이 아니다. 수렴·공차 통과 7건과 recurrence/종료 경계를 검증하기 위한
intentional `max_iterations` 3건으로 구성된다.

따라서 이 계약은 7건의 이미 발행된 ResultIRV2 bridge를 v0.2.42 audited family
authority와 결속하고, 나머지 3건에는 `source_not_converged` 비발행 disposition을
기록한다. 미수렴 case를 `result_ir_ready=true` 또는 `solution_ready=true`로
승격하지 않는다.

## Fixed package 진실표

| disposition | slot |
| --- | --- |
| `ready_result_ir_v2` | `frame_single_axial` |
| `ready_result_ir_v2` | `frame_single_weak_axis_bending` |
| `ready_result_ir_v2` | `frame_single_strong_axis_bending` |
| `ready_result_ir_v2` | `frame_single_torsion` |
| `not_issued_nonconverged` | `frame_single_rotated_local_axis_bending` |
| `ready_result_ir_v2` | `frame_serial_later_column` |
| `ready_result_ir_v2` | `truss_single_axial` |
| `ready_result_ir_v2` | `recurrence_initial_or_early_terminal` |
| `not_issued_nonconverged` | `recurrence_later_restart_partial_final_cycle` |
| `not_issued_nonconverged` | `recurrence_exact_full_final_cycle_guard` |

세 비발행 행은 모두 CPU reference와 retained model-case가
`status=max_iterations`, `termination_code=max_iterations_exhausted`, solver 및
authoritative-plan tolerance false인 경우다. Direct solution이나 재해석 결과로 이 행을
채우면 retained HIP completion-export identity를 잃으므로 허용하지 않는다.

## 계약 체인

```text
live v0.2.42 exact 10-slot audited result (factory entry/exit only)
  + seven exact issued v0.2.43 ResultIRV2 bridges
  + package fixture registry v1
  -> registry-order canonical 10-row disposition
  -> 7 ready rows: case / plan / export / device / state / ResultIR hash binding
  -> 3 nonconverged rows: exact termination and ResultIR absence reason
  -> detached audited receipt + seven bridge objects
  -> process-local final issuance gate
```

Factory는 audited result를 시작, 조립 전, 최종 조립 완료 뒤 발행 직전에 재검증하고,
retained audited graph에서 case를 직접 파생한다. Caller가 case나 slot label을 제공하지
못하게 하며 입력 bridge 순서는 무시하고 registry slot 순서로 canonicalize한다. 각
bridge는 약한 키 레지스트리가 발행한 비재사용 bare token으로 exact live model-case와
결속한다. Token은 context를 보유하지 않고 bridge seal/issuance에만 남으므로 CPython
`id()` 재사용과 직렬값이 같은 다른 run의 splice를 모두 거부한다. Ready 행마다 다음을
교차 검증한다.

- audited observation의 case, triple, completion-export receipt/payload 및 device identity
- exact retained model-case의 `ExecutionPlanV2` 객체와 plan ID/hash
- ResultIRV2 source provenance의 case/export/device binding
- accepted -> evaluated trial -> committed StateIR hash
- result ID, ResultIR hash, numerical/array descriptor binding
- projection의 추가 device operation, D2H, solve, export 및 fallback `0`

Factory 종료 뒤 aggregate는 live audited result나 transfer/ordinal contexts를 보유하지
않는다. Detached audited receipt와 7개 bridge만 보유하고, validator는 fresh package
registry, audited receipt, 각 bridge의 post-close validator 및 exact factory issuance를
재생한다. Serialized receipt 단독은 live hardware provenance가 아니다.

## 규모와 메모리 경계

| 집합 | slot | `G` | `E` | `F` | `nnz` |
| --- | ---: | ---: | ---: | ---: | ---: |
| ResultIRV2 ready | 7 | 90 | 8 | 43 | 1,116 |
| nonconverged, 미발행 | 3 | 72 | 9 | 54 | 1,080 |
| fixed package 전체 | 10 | 162 | 17 | 97 | 2,196 |

Ready 7건에 실제 materialize되는 여섯 ResultIR raw array는
`24G + 104E + 8F = 3,336` bytes이고, detached bridge가 별도로 보유하는 raw
solution/residual payload는 `16F = 688` bytes다. 미수렴 3건의 이론상 ResultIR array
`3,096` bytes는 materialize하지 않는다. 따라서 전체 10건의 이론값 `6,432` bytes를
실제 발행량 또는 10/10 ResultIR 증거로 사용하지 않는다.

이 수치는 sparse result materialization payload일 뿐 Python object overhead, StateIR,
plan, solve/export, peak RSS 또는 end-to-end 복잡도를 포함하지 않는다. Solver 전체
`O(N)`이나 speedup 증거가 아니다.

## 실행 및 claim 경계

Aggregate factory는 ResultIR bridge builder, completion export, HIP/native/device solver 또는
RTC/native API를 호출하지 않는다. 이미 발행된 seven bridge와 audited authority를 결속한다.
단, package registry의 authoritative validation은 deterministic CPU reference fixture를
재생할 수 있다. 따라서 `result_ir_projection_additional_solve_count=0`은 retained completion을
ResultIR로 투영하는 경로의 추가 native/device solve가 0이라는 뜻이며, registry-validation
CPU reference replay 0을 뜻하지 않는다. 이 경계는
`registry_validation_cpu_reference_replay_zero_proven=false`로 명시한다.

이 계약이 true로 만드는 것은 다음 두 항목뿐이다.

- exact fixed 10-slot disposition이 7 ready / 3 nonconverged 비발행으로 검증됨
- seven converged case의 ResultIRV2가 audited family lineage와 결속됨

다음은 계속 false 또는 pending이다.

- exact package 10/10 ResultIRV2 또는 all-ten solution-ready
- 이 v0.2.44 receipt 자체에 미수렴 partial iterate DiagnosticIR 포함
- 별도 all-converged fixture registry
- actual external `gfx1100`
- GPU-side reaction/member-force/energy recovery
- process-wide activity 또는 broad iteration-host-copy-zero
- standalone/signed provenance, promotion, commercial readiness
- solver/end-to-end `O(N)` 또는 speedup
- nonlinear, dynamic, shell, solid, contact 해석

## 구현 및 검증 자산

- `src/structural_analysis/engine_v2/assembly_backend/fgmres_model_family_result_ir_disposition_v1.py`
- `src/structural_analysis/schemas/hip_fgmres_model_family_result_ir_disposition_v1.schema.json`
- `tests/test_engine_v2_hip_fgmres_model_family_result_ir_disposition_v1.py`
- `tests/test_engine_v2_hip_fgmres_model_family_parity_v2_hardware.py`

Focused adversarial contract는 canonical/reversed input, 7개 bridge 각각의 거부와 강제
주입, 누락·중복·foreign 입력, exact/coherent clone, plan/provenance drift,
bridge/aggregate issuance transplant, serially identical cross-run splice, source race/swap,
schema/hash/claim, context close 뒤 검증 및 aggregate 연산 금지를 포함해
focused `23 passed`를 통과했다. Identity-token model-case/ResultIR, disposition,
capability 및 공개 API 최종 통합 검증은 `91 passed in 116.59s`를 통과했고,
capability/FGMRES-public/ResultIRV2-public 부분 집합은 `19 passed`다. Current-source actual
local `gfx1030` 통합 gate는 CPU fallback 없이 `1 passed in 7820.35s (2:10:20)`로
통과했다. 이 한 실행은 v0.2.42 exact 10-slot audited totals, v0.2.43 converged 7개
ResultIRV2 bridge, v0.2.44 canonical `7 ready_result_ir_v2 + 3
not_issued_nonconverged` disposition과 context close 뒤 detached validation을 함께
확인했다. 이 결과는 unsigned 비영속 작업 세션 관찰이며 10/10 ResultIRV2 ready,
standalone/signed provenance 또는 promotion 증거가 아니다.

## 다음 단계

1. **Current-source hardware 완료:** actual local `gfx1030` 10-slot harness에서 기존
   solve/export를 재사용해 수렴 7건의 bridge만 발행하고, 7/3 aggregate를 context close
   뒤 다시 검증했다.
2. **v0.2.47 contract/harness 완료:** 종료·failure 의미론을 검증하는 현 registry v1과
   canonical 7-ready/3-not-issued disposition을 유지한 채 별도 all-converged registry와
   exact 10/10 ResultIR vertical slice를 구현했다. Required actual local `gfx1030` gate는
   CPU fallback 없이 `1 passed in 1087.52s (0:18:07)`로 통과했고 process peak RSS는
   `450,868 KiB`였다. 과거 `5757.94s` 및 current-source `7820.35s`
   termination-registry 실행을 이 증거로 재사용하지 않는다.
3. **v0.2.45 additive companion 완료:** ResultIRV2를 완화하지 않고 nonconverged
   partial iterate를 `solution_ready=false`인 별도 DiagnosticIR 계약에 결속했다.
   UI 소비와 재시작 checkpoint 자격은 여전히 후속 범위다.
4. External `gfx1100`, signed evidence 및 promotion은 별도 gate로 유지한다.
