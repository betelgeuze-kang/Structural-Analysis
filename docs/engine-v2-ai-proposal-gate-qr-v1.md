# Engine v2 Phase 0 AI proposal·physics gate·QR memory v1

- 문서 상태: Phase 0 구현 계약
- 제안 계약: `structural-analysis-ai-correction-proposal.v1`
- gate receipt: `structural-analysis-ai-proposal-gate-receipt.v1`
- QR memory: `structural-analysis-fixed-rank-qr-memory.v1`
- 주장 경계: calibrated AI, warm-start 가속, online learning, HIP solver 또는 상용 해석 준비도의 증거가 아니다.

## 1. 목적

이 slice는 AI 출력이 해석 상태를 직접 바꾸지 못하도록 다음 최소 안전 경로를
구현한다.

```text
validated ExecutionPlan + committed StateIR + FixedRankProjection
  -> immutable AICorrectionProposal (D Q y)
  -> ephemeral StateIR trial
  -> full K u - F / Jacobi-scaled residual / energy / BC /
     stateless linear-elastic element-law replay
  -> exact rollback to the original accepted object
  -> rejected in Phase 0 because OOD/calibration evidence is absent
  -> untouched authoritative CPU solve is executed for shadow parity
```

AI proposal은 `initial_guess` overlay일 뿐이며 `ResultIR`, final result, commit 또는
안전 판정의 권한을 갖지 않는다.

## 2. 좌표·단위 계약

자유도 강성을 \(K_{ff}\)라 할 때 Jacobi energy map은 다음과 같다.

\[
D = \operatorname{diag}(K_{ff})^{-1/2}, \qquad u_f = D x
\]

`FixedRankProjection` 기저 \(Q\)는 \(x\) 좌표에서 직교이며 proposal은 다음을
byte-exact semantic replay로 검증한다.

\[
x_{corr}=Qy, \qquad \Delta u_f = DQy
\]

\(D\)의 단위를 고려하면 \(x\), \(y\), \(Qy\)는 무차원이 아니다. 계약은 이를
`sqrt_joule_energy_coordinate`로 표기한다. `correction_free`는 global DOF에
따라 `m_or_rad_by_global_dof`다. trust radius도 동일한 제곱근-에너지 좌표에
있다.

## 3. `AICorrectionProposal` 불변식

`build_phase0_ai_proposal()`은 다음을 검증한 후 immutable little-endian FP64
아티팩트를 만든다.

- ModelIR content, numeric/entity/artifact buffer, plan/operator/pattern/partition hash
- committed base `StateIR` ID, epoch, hash
- exact `FixedRankProjection` hash, retained rank, rank cap `<=16`
- \(Q^TQ\) Gram condition과 trust radius 내 `||y||_2`, `||Qy||_2`
- `correction_scaled=Qy`, `correction_free=DQy`의 바이트 및 descriptor hash
- `overlay_only=true`, `final_result=false`, `direct_state_commit=false`
- full residual, energy, BC, constitutive replay required
- `ood_status=not_evaluated`, `statistical_calibration=false`,
  `acceptance_eligible=false`

변조된 배열 descriptor나 aggregate hash만 갱신한 semantic 변조도 \(Qy\) 및
\(DQy\) 재계산에서 거부된다.

## 4. full-physics gate와 rollback

`evaluate_ai_proposal_gate()`는 accepted displacement에 자유도 correction만 scatter한
임시 trial을 열고 다음을 재계산한다.

1. full residual \(R(u)=Ku-F\), sign `internal_minus_external`
2. scaled free residual \(\lVert D R_f\rVert_2\); load-normalized proxy를 사용하지 않음
3. total potential energy \(\Pi(u)=\frac12u^TKu-u^TF\)
4. constrained-DOF increment의 exact zero
5. element local stiffness/transform으로 다시 assembly한 stateless linear-elastic
   internal force·strain energy와 compiled global operator의 일치
6. trust, rank, Gram condition, OOD/calibration policy

gate는 성공·실패가 어떻든 `commit_trial_state()`를 호출하지 않고
`rollback_trial_state()`가 정확히 기존 accepted 객체를 반환했는지, 객체 identity,
state hash, displacement hash가 변하지 않았는지를 receipt에 남긴다. replay
예외 경로도 `finally` rollback을 실행한다.

현재 proposal은 통계적 calibration과 OOD 분류기가 없으므로 물리 지표가 좋아져도
gate status는 `rejected`다. 주요 reason code는 `ood_not_evaluated`,
`statistical_calibration_missing`이다. gate receipt v1의 schema와 validator도
`not_evaluated`/calibration `false`/status `rejected`로 고정한다. 향후 calibrated
proposal은 calibration evidence를 해시에 결박한 새 계약 버전으로만 추가한다.

detached receipt의 SHA-256은 전자서명이 아니다. expected plan/state/proposal 없이
호출하는 validator는 schema와 내부 산식·binding의 자기일관성만 확인한다. promotion
또는 authority 판단에는 세 expected input을 모두 제공해 full gate replay를 수행해야
한다. 현재 v1은 detached receipt에도 eligible authority를 허용하지 않는다.

## 5. shadow isolation

`run_ai_shadow_v1()`은 gate를 먼저 실행한 뒤 기존 authoritative direct CPU
solver를 동일한 buffer/plan으로 두 번 실행한다.

- 현재 direct solver는 initial-guess API가 없어 proposal을 소비하지 않는다.
- 따라서 `ai_on`은 proposal이 관찰된 shadow label이지 warm start가 적용된
  실행이 아니다.
- backend identity, native result, displacement, residual, reaction, element force/energy,
  state lineage, ResultIR manifest/hash, receipt-chain hash가 bit-identical해야 한다.
- gate, AI-off, AI-observed run은 buffer 4-hash와 plan/operator/pattern/partition이
  정확히 같아야 한다.
- direct-solver v1에서는 proposal base가 결정론적 epoch-0 initial state와 같아야
  하며 이후 committed state warm start는 fail-closed다.
- timing을 측정하지 않고 speed claim을 금지한다.

이 shadow의 증명은 “AI 경로를 제거해도 해석 결과가 변하지 않는다”는
안전 경계다. AI 가속, 수렴 개선 또는 정확도 증거가 아니다.

## 6. solver-approved fixed-rank QR memory

`FixedRankQRMemory`는 향후 local no-backprop update에 사용할 수 있는 제한된
teacher-mode memory다.

- `validate_linear_static_run()`을 전체 통과한 `ready` `LinearStaticRun`만 teacher로 허용
- 정확한 물리 mode:
  `(committed_displacement-initial_displacement)[free_dofs]`
- plan/operator/pattern/partition exact binding
- `rank_cap<=16`, deterministic FIFO eviction, rolling provenance chain
- 각 update마다 원본 물리 mode로 `build_fixed_rank_projection()` 재실행
- immutable raw modes/basis, schema/hash/operation-count replay
- storage `O(Nk)`, basis rebuild `O(Nk^2)`, dense \(QQ^T\) 없음
- reverse-mode autograd, gradient update, legacy AI runtime import 없음

중요하게도 이 memory는 아직 RLS/Kalman/readout parameter update를 수행하지 않는다.
따라서 “no-backprop online learning 완료”로 표기하지 않고
`solver_approved_qr_correction_memory_not_training`으로 경계를 고정한다.

## 7. 사용 순서

```python
from structural_analysis.engine_v2 import (
    build_fixed_rank_projection,
    build_phase0_ai_proposal,
    create_fixed_rank_qr_memory,
    create_initial_state,
    evaluate_ai_proposal_gate,
    run_ai_shadow_v1,
    update_fixed_rank_qr_memory_from_run,
)

accepted = create_initial_state(plan)
projection = build_fixed_rank_projection(plan, physical_candidate_columns)
proposal = build_phase0_ai_proposal(
    plan,
    accepted,
    projection,
    coefficients_y,
    trust_radius,
)
gate = evaluate_ai_proposal_gate(plan, accepted, proposal)
shadow = run_ai_shadow_v1(buffers, plan, accepted, proposal)

memory = create_fixed_rank_qr_memory(plan, rank_cap=16)
memory = update_fixed_rank_qr_memory_from_run(memory, authoritative_run)
```

`gate.status`가 `rejected`여도 shadow authoritative solver는 계속 실행된다. QR memory에는
proposal/trial/gate receipt가 아니라 완전히 검증된 authoritative run만 넣을 수 있다.

## 8. 검증과 미완료 경계

집중 검증은 다음을 포함한다.

- strict Draft 2020-12 schema와 semantic rehash tamper 거부
- \(Qy\), \(DQy\), 제곱근-에너지 단위, trust/rank 검증
- \(Ku-F\), \(\lVert DR_f\rVert_2\), potential energy, BC, element-law replay
- reject 및 replay exception에서 exact rollback
- OOD/calibration fail-closed
- cross-plan shadow splicing 거부와 AI-off/observed bit identity
- authoritative-run-only teacher, FIFO, tamper, no-autograd audit

다음은 아직 미구현이다.

- E(3)-equivariant feature runtime, causal temporal state, calibrated OOD/UQ
- projected least-squares/RLS/Kalman coefficient update
- initial guess를 실제로 소비하는 iterative CPU/HIP solver와 수렴 가속 검증
- nonlinear constitutive history, contact/MPC/prescribed nonzero BC gate
- HIP full residual/JVP replay와 CPU/HIP parity
- end-to-end time/memory complexity slope와 실제 사용자 프로젝트 shadow

따라서 이 구현으로 Phase 0 전체, AI gap, 상용 솔버 준비도를 폐쇄하지
않는다.
