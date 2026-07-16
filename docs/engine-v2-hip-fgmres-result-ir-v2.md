# Engine v2 HIP FGMRES ResultIR v2

## 판정

`v0.2.43`은 retained converged HIP FGMRES 단일 model-case completion을
`ExecutionPlanV2 -> StateIR -> ResultIRV2`로 연결하는 contract-only 후보
milestone이다. 구현 계약과 CPU sparse recovery 경로는 current source에서 검증됐다.
비재사용 exact-case identity token 패치 전 source snapshot은 actual local `gfx1030`
단일 모델 required gate를 통과했다. Current-source actual local `gfx1030` 통합 gate도
CPU fallback 없이 `1 passed in 7820.35s (2:10:20)`로 통과해 converged 7개 bridge와
context close 뒤 validation을 확인했다. Fixed package 10/10 solution-ready와 external
`gfx1100`은 아직 pending이다.
다만 현재 fixed package 10-slot 중 3개는
의도적으로 `max_iterations` 종료를 검증하는 case이므로, 현 ResultIRV2 계약으로
10개 모두를 `result_ir_ready=true`로 만드는 것은 허용되지 않는다.

이 milestone은 기존 HIP solve나 completion export를 다시 실행하지 않는다. Live
factory가 model-case parity의 private process-local authority를 검증하고 이미 host에
export된 `solution_x`와 `true_residual` bytes만 소비한다. 기존 completion export의
blocking D2H 세 번(`solution_x`, `true_residual`, `solve_record`)은 그대로 존재하며,
retained-source factory direct-call contract에서 추가하는 device operation, D2H, solve,
export, fallback은 모두 `0`이다. 이는 transitive/process-wide 계측값이 아니다.

따라서 이 exact retained converged single-case 범위에서만
`ResultIRV2Claims.result_ir_ready=true`다. 이는 upstream completion/model-family
receipt의 historical `result_ir_ready=false`를 변경하지 않고, general solver·all-10·
hardware promotion readiness로 전파되지 않는다.

Public generic `build_result_ir_v2()`는 물리 복원을 통과해도 항상
`result_ir_ready=false`를 발행한다. Bridge는 두 번째 live-authority capture까지 성공한
뒤 비공개 process-local mint로 반환된 exact `ResultIRV2` object identity에만 true 권한을
부여한다. `replace`, direct construction, coherent rehash 또는 standalone manifest는 이
identity를 보존하지 못해 generic validator에서 true 위조로 거부된다. 이는 동일
프로세스의 hostile code에 대한 보안 경계나 tamper-proof mint 주장이 아니다.

## 계약 체인

```text
retained converged HIP model-case authority (live factory only)
  -> already-exported solution_x / true_residual bytes
  -> exact retained sparse ExecutionPlanV2
  -> full displacement: free <- solution_x, constrained <- +0.0
  -> full residual: ExecutionPlanV2.residual(u) = K*u-F
  -> reaction: constrained residual, free exact +0.0
  -> local member force / element strain energy
  -> trial StateIR -> committed StateIR
  -> descriptor-only ResultIRV2
  -> detached source seal + retained plan/states
```

Factory는 live source를 시작과 CPU recovery 종료 뒤 두 번 capture해 같은 authority인지
확인한다. Converged native HIP source, exact plan/object lineage, model-case parity receipt,
terminal observation, completion-export receipt/payload, device identity, architecture/device,
raw solution/residual payload hash를 교차 결속한다. Source authority가 중간에 교체되거나
수치 bytes가 변하면 ResultIR을 발행하지 않는다.

## 수치 복원

ResultIR v2는 다음 여섯 배열을 immutable bytes-backed C-order `<f8`로 보유한다.
모든 signed zero는 `+0.0`으로 canonicalize되고 각 배열은 data/content hash를 갖는다.

| 배열 | shape | 정의 |
|---|---:|---|
| `displacements_si` | `[node, 6]` | full node-major displacement/rotation |
| `residual_si` | `[node, 6]` | full `K*u-F` |
| `reactions_si` | `[node, 6]` | constrained residual, free zero |
| `element_end_forces_local_si` | `[element, 2, 6]` | `k_local*u_local` |
| `element_strain_energy_j` | `[element]` | `0.5*u_local^T*f_local` |
| `exported_free_residual_si` | `[free]` | HIP-exported `F-K*u` |

전역 dense matrix를 만들거나 CPU/GPU linear solve를 호출하지 않는다. Full residual은
`ExecutionPlanV2.residual()`의 CSR replay로 만들고, member force와 element energy는
plan이 보유한 `element_global_dofs`, global-to-local transform, local stiffness만
사용한다. Validator는 다음을 fail-closed로 재생한다.

- constrained displacement exact zero
- trial/committed StateIR의 plan binding, direct-parent lineage와 vector 보존
- scaled full/free residual 및 exported residual이 plan tolerance 이하
- exported `F-K*u`와 `-(K*u-F)[free]`의 `atol=1e-12`, `rtol=1e-8` 부호/수치 일치
- reaction의 constrained partition과 free DOF exact `+0.0`
- local end force와 element energy
- element 합 = global strain energy
- global strain energy = half external work + half residual work

## 직렬화와 provenance 경계

Manifest는 배열 값을 JSON list로 복제하지 않는다. Shape, layout, axis/component 단위,
byte length, data/content hash만 직렬화하는 descriptor-only 형식이다. 프로세스 내부
structural/physics validator는 private retained 배열 bytes를 다시 검증한다.

Process-local ready authority는 manifest에 직렬화하지 않는다. Bridge가 반환한 exact live
object는 detached physics replay 뒤 true claim을 유지하지만, public standalone manifest
validator는 `result_ir_ready=true`를 독립적으로 인증하지 않고 fail-closed한다.

Prepublication compatibility decision: 이 ResultIR v2 code/schema는 `origin` tracking
branch에 아직 게시되지 않은 unpublished candidate다. Generic `result_ir_ready=true`
의미는 first publication 전에 generic ready false/private exact-object ready로 재정의했다.
따라서 이전 local v2 ready-true manifest와 현재 ready-false manifest는 양방향 호환되지
않으며, legacy local persisted v2에 대한 migration 또는 acceptance를 제공하지 않는다.
실제 persisted artifact가 발견되면 명시적 v3 contract와 migration을 구현·검증할 때까지
ResultIR publication을 금지한다.

Raw HIP payload hash는 signed-zero canonicalization 이전의 exact export bytes를 결속하며
live factory와 detached source seal이 검증한다. Generic ResultIR validator가 raw HIP hash를
canonical ResultIR array hash로 바꾸어 해석하지 않는다.

Factory 종료 뒤 bridge result는 exact sparse plan, initial/trial/committed StateIR,
canonical ResultIR와 value-only source seal을 보유하므로 HIP context close 뒤에도 detached
validation이 가능하다. 그러나 detached validation은 보존된 값과 hash chain의
일관성만 증명한다. Serialized receipt 단독의 live hardware provenance나 서명된 실행
증거가 아니다.

Live factory와 상위 family composition은 factory-issued model-case를 weak-key registry의
비재사용 bare token으로 결속한다. Bridge seal과 process-local issuance는 token만
보유하며 model-case나 export context를 강하게 보유하지 않는다. 따라서 source가
수거된 뒤의 CPython `id()` 재사용이나 exact-value clone은 live-case binding을 얻지
못한다.

## 전송 및 실행 직접 호출 계약 경계

| 항목 | retained-source factory direct-call surface 추가량 |
|---|---:|
| device operation | `0` |
| blocking/async D2H | `0` |
| device solve | `0` |
| completion export | `0` |
| fallback | `0` |

위 표는 이미 host에 보존된 source bytes를 소비하는 factory의 direct-call surface와
provenance literal을 고정한 contract다. Transitive helper/runtime 활동을 계측한 값이 아니며
process-wide operation ledger도 아니다. Upstream completion export가 이미 수행한 blocking
D2H `3`회를 `0`으로 재분류하지 않고, 전체 solve setup/teardown 또는 process-wide ROCm
activity가 zero라는 주장도 아니다.

## 복잡도와 메모리 경계

Global DOF 수를 `G`, CSR stored entry 수를 `nnz`, element 수를 `E`, free DOF 수를
`F`라 하면 result materialization은 `O(G + nnz + 144E)`이다. 여섯 raw result array의
정확한 payload 크기는 `24G + 104E + 8F` bytes다. Descriptor-only manifest는 이 수치
배열을 JSON으로 다시 보유하지 않는다.

Detached bridge source seal은 이 ResultIR 배열과 별도로 raw HIP `solution_x`와
`true_residual` exact bytes `16F`를 추가 보유하며, 세 StateIR snapshot과 plan reference도
retained한다. 따라서 bridge retained state는 여전히 `O(G+E)`이지만 `16F`를 위의
ResultIR 여섯 배열 공식에 합산하거나 ResultIR 자체의 중복 JSON payload로 해석하지
않는다.

이 식은 retained sparse plan에서 한 번 수행하는 결과 복원 비용/배열 payload만
설명한다. FGMRES solve, plan compile/assembly, HIP setup/export, Python object overhead,
StateIR retained vectors와 peak RSS를 포함하지 않으며 solver 또는 end-to-end `O(N)`,
near-linear scaling, latency, speedup 증거가 아니다.

## 명시적 제외

다음은 계속 false 또는 미검증이다.

- nonconverged/failed HIP terminal 결과의 성공 ResultIR 발행
- fixed package 10-slot의 10/10 `result_ir_ready=true` 승격
- 이 v0.2.43 ResultIR bridge 자체에서 3개 intentional `max_iterations` case의
  solution-ready ResultIR 또는 DiagnosticIR 발행
- actual external `gfx1100` ResultIR
- process-wide activity 또는 broad iteration-host-copy-zero
- transitive helper/runtime operation 계측 또는 factory 밖 process-wide zero
- GPU-side reaction/member-force/energy recovery
- standalone detached/serialized provenance authenticity
- hostile same-process private mint/object-identity 공격 저항성
- signed evidence, promotion eligibility, commercial readiness
- solver/end-to-end `O(N)` 또는 speedup
- nonlinear, dynamic, shell, solid, contact 해석 결과

## 구현 및 검증 자산

- `src/structural_analysis/engine_v2/contracts/result_ir_v2.py`
- `src/structural_analysis/schemas/result_ir_v2.schema.json`
- `src/structural_analysis/engine_v2/assembly_backend/fgmres_result_ir_v2.py`
- `tests/test_engine_v2_result_ir_v2.py`
- `tests/test_engine_v2_hip_fgmres_result_ir_v2.py`
- `tests/test_engine_v2_result_ir_v2_public_api.py`
- `tests/test_engine_v2_hip_fgmres_model_case_parity_hardware_v1.py`
- `tests/test_engine_v2_capability_matrix.py`

Generic contract `16 passed`, bridge contract `13 passed`(합계 `29 passed`), public API
`3 passed`, capability matrix `9 passed`, model-case downstream authority `24 passed` 및 이
다섯 파일 combined `65 passed in 29.31s`를 확인했다. 첫 actual run은 production global
context가 매 검증마다
fresh outer source-authority wrapper를 반환하는 수명주기를 드러냈다. Wrapper 객체 identity를
고정값으로 오해한 검증을 제거하고, 봉인된 source snapshot과 retained plan/runtime/buffer
identity를 계속 재생하도록 수정했다. 이후 required local `gfx1030` gate는 CPU fallback 없이
`1 passed in 169.10s (0:02:49)`로 통과했다.

위 `169.10s` 결과는 비재사용 identity-token 패치 전 source snapshot의 unsigned 비영속
단일 모델 역사 관찰이다. Token-hardened current source는 이후 exact 10-slot 통합 gate를
CPU fallback 없이 `1 passed in 7820.35s (2:10:20)`로 통과했다. 같은 실행에서 converged
7개 ResultIRV2 bridge를 actual `gfx1030` lineage에 결속하고 context close 뒤 모두 다시
검증했다. 이 current-source 결과도 unsigned 비영속 관찰이며 fixed package 10/10
solution-ready, external `gfx1100`, standalone/signed provenance 또는 promotion 증거가 아니다.

## 다음 단계

1. **Current-source hardware 완료:** 통합 10-slot harness에서 동일 solve/export lineage의
   converged 7개 ResultIR v2 bridge를 actual local `gfx1030`으로 검증하고 context close 뒤
   다시 검증했다.
2. **완료:** Exact package 10-slot을 7개 converged ResultIRV2와 3개 intentional
   `max_iterations` 비발행 disposition으로 결속했고 solve/export를 중복하지 않았다.
3. **DiagnosticIR 분리는 v0.2.45에서 완료:** 미수렴 partial iterate는
   solution-ready ResultIRV2와 분리된 additive DiagnosticIR로 보존한다.
4. **v0.2.47 contract/harness 완료:** 별도 all-converged registry와 exact 10/10
   ResultIR vertical slice를 구현했고, required actual local `gfx1030` gate가 CPU fallback
   없이 `1 passed in 1087.52s (0:18:07)`로 case/bridge `10/10`, family, aggregate와
   post-close validation을 통과했다. Process peak RSS는 `450,868 KiB`였다. 기존 7/3
   역사적 진실은 바꾸지 않으며 termination-registry의 과거 `5757.94s` 및
   current-source `7820.35s` 실행을 이 증거로 재사용하지 않는다.
5. External `gfx1100`과 signed release/hardware evidence는 별도 승격 gate로 유지한다.
