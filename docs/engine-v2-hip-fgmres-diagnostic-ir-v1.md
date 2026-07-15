# Engine v2 HIP FGMRES DiagnosticIR v1

## 판정

`v0.2.45`는 exact package registry의 intentional `max_iterations` 3건을
성공 `ResultIRV2`로 위장하지 않고, 미수렴 partial iterate와 종료 이력을
별도 `DiagnosticIRV1`로 보존하는 contract-only 후보 milestone이다. 기존
v0.2.44의 canonical `7 ready_result_ir_v2 + 3 not_issued_nonconverged`
진실표는 변경하지 않는다.

공개 generic builder는 plan/StateIR/residual/rollback을 재생하더라도 serialized
provenance만으로 live HIP source를 인증할 수 없으므로
`diagnostic_ready=false`를 발행한다. `partial_iterate_preserved`,
`nonconverged_max_iterations_verified`, `restart_history_preserved`도 generic
경계에서 false다. 두 번째 live-authority capture를 통과한 HIP bridge가
비공개 process-local exact-object issuer를 호출한 그 객체만 이 네 claim을
true로 가진다. 이 scoped `diagnostic_ready=true`는 미수렴 source를
진단용으로 검증했다는 뜻일 뿐이다. `solution_ready`, `result_ir_ready`,
반력, 부재력, 에너지, code check, 최적화 소비, 재시작 checkpoint,
상용화와 promotion claim은 모두 false다.

DiagnosticIR v1의 배열·StateIR·종료 의미론은 backend-independent하게 재생할 수
있지만, 현 v1 provenance profile은 의도적으로 exact HIP/`gfx` source와 device
lineage에 한정한다. CPU나 다른 backend provenance를 같은 schema로 가장하지 않으며,
공용 provenance union은 후속 versioned profile로 분리한다.

## 대상 종료 케이스

| slot | CPU/HIP terminal | policy boundary |
| --- | --- | --- |
| `frame_single_rotated_local_axis_bending` | `max_iterations / max_iterations_exhausted` | `M=6`, `I=5`, `rtol=1e-30` |
| `recurrence_later_restart_partial_final_cycle` | `max_iterations / max_iterations_exhausted` | `M=2`, `I=5`, `rtol=1e-30` |
| `recurrence_exact_full_final_cycle_guard` | `max_iterations / max_iterations_exhausted` | `M=2`, `I=4`, `rtol=1e-30` |

세 건 모두 solver L2와 authoritative plan scaled-Linf tolerance를 통과하지
못한다. 이는 현 레지스트리가 종료·recurrence 경계를 일부러 검증하기
위한 결과이며 모델이 해석 불가능하다는 뜻은 아니다. 제품의 10/10
solution gate는 현 종료-회귀 registry를 수정하지 않고 별도
all-converged registry에서 수행한다.

## 계약 체인

```text
exact factory-issued HIP model-case authority (live factory only)
  -> already-exported solution_x / true_residual / solve_record
  -> terminal solve-record detached decode
  -> exact retained sparse ExecutionPlanV2
  -> full partial iterate: free <- solution_x, constrained <- +0.0
  -> full diagnostic residual: K*u-F
  -> canonical initial accepted StateIR
  -> evaluated trial StateIR
  -> rollback result is the exact accepted StateIR
  -> no committed StateIR
  -> descriptor-only DiagnosticIRV1
  -> detached raw source seal + exact process-local issuance
```

HIP bridge factory는 model-case parity가 발급한 비재사용 bare identity token을
재사용한다. 시작과 CPU sparse 진단 재생 후 live authority를 두 번
capture하여 exact case, plan, CPU result, terminal observation, completion export,
device identity, raw three-payload bytes가 동일한지 확인한다. 중간에 source나
payload가 바뀌면 아무 ready DiagnosticIR도 발행하지 않는다. 두 번째
capture 동일성 확인 후 seal 생성 전에만 private issuer를 호출한다.
`dataclasses.replace`, shallow/deep copy, 직접 생성, coherent rehash로 만든
true receipt는 exact-object identity authority를 가지지 못해 structural/physics
validator 모두에서 거부된다. Detached manifest도 ready true를 유지할 수 없다.
이 identity seal은 정직한 process-local 계약 경계이며 hostile same-process code에
대한 보안 경계는 아니다.

Factory 종료 후 bridge는 model-case, export context, runtime을 보유하지
않는다. Exact sparse plan, accepted/trial StateIR, canonical DiagnosticIR,
raw `solution_x`/`true_residual`/`solve_record`, value-only policy와 발행 seal만
보존한다. 따라서 HIP context close 후에도 solve record decode와 plan residual,
state lineage, raw hash를 재생할 수 있지만, 이는 standalone hardware provenance나
서명된 증거가 아니다.

## 배열과 StateIR 의미론

DiagnosticIR v1은 immutable bytes-backed C-order `<f8` 배열 세 개만
보유한다. JSON manifest에는 배열 값을 복제하지 않고 descriptor와
data/content hash만 든다. Descriptor-only manifest validator는 generic
`diagnostic_ready=false` 경계만 허용하며 standalone source authenticity를 주장하지 않는다.

| 배열 | shape | 정의 |
| --- | ---: | --- |
| `partial_displacement_si` | `[global_dof]` | 최종 true-residual checkpoint의 canonical global-DOF partial iterate |
| `residual_si` | `[global_dof]` | canonical global-DOF full `K*u-F` diagnostic residual |
| `exported_free_residual_si` | `[free]` | HIP-exported `F-K*u` |

제약 DOF는 exact positive zero로 canonicalize한다. Validator는 full residual이
`ExecutionPlanV2.residual(u)`와 일치하고 exported residual이
`-(K*u-F)[free]`와 일치하는지 확인한다. 반력, element end force,
strain energy는 계산하지 않고 발행하지 않는다.

Accepted state는 exact plan의 canonical epoch-0 zero committed StateIR이다. Partial
iterate는 epoch-1 trial로만 평가하고 `rollback_trial_state()`가 같은 accepted
객체를 반환하는지 확인한다. `commit_trial_state()`는 bridge 경로에서
호출하지 않으며 `committed_state_hash=null`을 유지한다.

## 종료 이력과 provenance

Receipt는 FGMRES policy, iteration/restart/operator/preconditioner counter, initial/final
residual metric과 populated restart history를 보존한다. HIP bridge는 detached
`solve_record`를 현 ABI로 다시 decode하여 status, termination code, counter,
metric, restart row가 발행 receipt와 같은지 확인한다. CPU reference 이력은
model-case parity가 이 HIP record와 이미 결속한 source witness로 사용한다.

Raw HIP payload hash는 signed-zero canonicalization 이전 exact export bytes를 결속한다.
이 hash를 canonical DiagnosticArray data hash와 같다고 가정하지 않는다.
Generic builder는 caller가 제공한 detached hash의 형식과 내부 계약만
검증하므로 raw-source preservation claim을 발행하지 않는다. Raw payload·solve
record·live case authority와의 exact 교차 결속은 HIP bridge가 담당한다.

## 연산·전송·메모리 경계

| 항목 | Diagnostic projection 추가량 |
| --- | ---: |
| device operation | `0` |
| D2H | `0` |
| native/device solve | `0` |
| completion export | `0` |
| fallback | `0` |
| StateIR commit | `0` |

위 `0`은 retained-source factory의 direct-call surface와 직렬화된 literal
counter 계약이다. Transitive helper, runtime 전체 또는 process-wide device/D2H/
solve/export/fallback/commit operation을 계측했다는 뜻이 아니다.

Projection은 retained sparse plan residual을 케이스당 한 번 재생하므로 CPU
operation zero를 주장하지 않는다. Upstream completion export의 기존 blocking
D2H `3`회도 지우지 않는다.

Family receipt의 `sparse_residual_replay_count=3`은 세 diagnostic slot 모두 sparse
residual replay 검증을 갖는다는 **논리적 coverage count**다. Factory와 post-close
validator가 같은 plan physics를 반복 검증할 수 있으므로 Python `plan.residual()`의
실제 호출 횟수나 CPU operation counter로 해석하지 않는다.

Global DOF를 `G`, free DOF를 `F`라 하면 slot별 DiagnosticIR의 세 배열
category exact raw payload는 `16G + 8F` bytes다. Fixed nonconverged family는
3 slots × slot당 3 arrays = aggregate 9 arrays이다. 세 slot의 합계
`G=72,E=9,F=54,nnz=1,080`에서 aggregate diagnostic 배열은 `1,584` bytes다.

Detached bridge source seal은 이 배열과 별도로 upstream raw export 전체를
보유한다. 케이스별 `360 + 792 + 720 = 1,872` bytes이며 이는
이미 수행된 D2H bytes의 detached copy이지 추가 device transfer가 아니다.
이 수치는 Python object overhead, plan/StateIR retained bytes, peak RSS, solve/assembly
시간을 포함하지 않으며 solver/end-to-end `O(N)`이나 speedup 증거가
아니다.

## Family companion

Additive family companion은 v0.2.42 audited live authority, v0.2.44 exact disposition
result, 3개 exact DiagnosticIR bridge를 결속한다. Caller 순서와 무관하게
registry 순서로 canonicalize하고 기존 nonconverged 행의
`result_ir_materialized=false`를 유지한다.

```text
7 converged slots -> ResultIRV2 ready
3 max_iterations slots -> DiagnosticIRV1 ready, ResultIRV2 not issued
10/10 disposition coverage -> true
10/10 solution ready -> false
10/10 ResultIRV2 ready -> false
all-converged registry verified -> false
```

## 명시적 제외

- 미수렴 partial iterate의 solution/ResultIR 승격
- 미수렴 state commit 또는 restart checkpoint 자격
- reaction/member-force/energy/code-check/design/optimization 소비
- 별도 all-converged 10/10 registry
- actual external `gfx1100`
- process-wide ROCm 활동 또는 broad iteration-host-copy-zero
- standalone/serialized provenance authenticity, signed evidence
- hostile same-process mutation/interposition 저항
- promotion eligibility, commercial readiness
- solver/end-to-end `O(N)`, latency 또는 speedup
- nonlinear, dynamic, shell, solid, contact 해석

## 구현 및 검증 자산

- `src/structural_analysis/engine_v2/contracts/diagnostic_ir_v1.py`
- `src/structural_analysis/schemas/diagnostic_ir_v1.schema.json`
- `src/structural_analysis/engine_v2/assembly_backend/fgmres_diagnostic_ir_v1.py`
- `src/structural_analysis/engine_v2/assembly_backend/fgmres_model_family_diagnostic_ir_v1.py`
- `src/structural_analysis/schemas/hip_fgmres_model_family_diagnostic_ir_v1.schema.json`
- `tests/test_engine_v2_diagnostic_ir_v1.py`
- `tests/test_engine_v2_hip_fgmres_diagnostic_ir_v1.py`
- `tests/test_engine_v2_hip_fgmres_model_family_diagnostic_ir_v1.py`
- `tests/test_engine_v2_diagnostic_ir_v1_public_api.py`
- `tests/test_engine_v2_hip_fgmres_model_family_parity_v2_hardware.py`

Current-source focused/public 4개 파일은 `42 passed in 380.25s (0:06:20)`, capability
matrix는 `9 passed`, v0.2.43~v0.2.45 인접 통합 suite는
`138 passed in 497.62s (0:08:17)`, hardware harness는 `1 test collected`를 확인했다. Real
gfx agent가 없는 환경에서 non-required gate는 `1 skipped`, required gate는
skip 없이 `1 failed`해 hardware agent 부재 시 fail-closed하는 것도 확인했다.

이후 token-hardened current source의 actual local `gfx1030` exact 10-slot 통합
required gate는 CPU fallback 없이 `1 passed in 7820.35s (2:10:20)`로 통과했다.
실행 전후 Engine v2 source/schema/fixture aggregate는
`sha256:5a977e48c7735b694e4b76752494c92bea89f69fb74c3bcb738a5a36b722b6cc`,
통합 hardware harness는
`sha256:3b0acb3ab1af894f5ef099c227614b54983f51857c1dce08e0def9977df00bde`,
공유 sealed-chain harness는
`sha256:660806190c2ba8b6b9a436126082f047881646ef413811760a771df9ddf11693`로
동일했다.
동일 solve/export lineage에서 7개 converged ResultIRV2와 3개 nonconverged
DiagnosticIRV1 bridge를 발행하고, family companion의 `7 ResultIR + 3 DiagnosticIR`,
`G=72,E=9,F=54,nnz=1,080`, 9 arrays/`1,584` bytes, detached raw `1,872`
bytes, upstream D2H `9/9/0`·`1,872` bytes와 projection 추가
device/D2H/solve/export/fallback/commit `0`을 검증했다. Context close 뒤 family
validator도 재통과했다. 이는 unsigned 비영속 작업 세션 관찰이며 standalone/signed
hardware provenance, external `gfx1100`, 10/10 ResultIRV2 solution readiness 또는
promotion/commercial evidence가 아니다.

## 다음 단계

1. **완료:** Current-source single-case·3-slot family DiagnosticIR hardware path를
   actual local `gfx1030` 통합 harness에서 검증했다.
2. **v0.2.47 contract/harness 완료:** 현 종료-회귀 registry와 7-result/3-diagnostic
   진실표를 유지하면서 10개 고유 ModelIR·실제 해석 tolerance를 갖는 별도
   all-converged registry와 exact 10/10 ResultIR vertical slice를 구현했다. 현재 host
   probe는 `gfx1030` ready이고 fallback false지만 신규 required actual `gfx1030` gate와
   peak RSS는 pending이고 과거 `5757.94s` 및 current-source `7820.35s`
   termination-registry 실행은 신규 all-converged 증거가 아니다.
3. External `gfx1100`, signed hardware/release evidence와 promotion gate는 별도로
   유지한다.
