# ADR-005: AI Proposal and Rollback Contract

- Status: accepted
- Date: 2026-07-10
- Deciders: Engine v2 architecture baseline

## Context

AI correction이 solver state를 직접 변경하면 실패/OOD 시 원본 해와 material history를 복원하기 어렵고, proxy residual 감소가 최종 평형으로 오인될 수 있다.

## Decision

- AI는 immutable `StateView`를 읽고 `AICorrectionProposal` overlay만 반환한다.
- proposal hook은 initial guess, Krylov seed, preconditioner/coarse enrichment, Newton direction, design action으로 제한한다.
- proposal에는 base model/state hash, target vector space, units/frame, trust/complexity budget, UQ/OOD, required replay를 포함한다.
- trial arena에서 적용한 뒤 full residual/energy/BC/constitutive/code replay가 모두 통과할 때만 atomic commit한다.
- 제품 runtime update는 reverse-mode autograd/backward graph를 사용하지 않고 local RLS/QR/Kalman 계열로 제한한다.

## Normative invariants

- AI proposal은 `final_result=true` 권한을 가질 수 없다.
- accepted state는 trial 평가 중 변경되지 않는다.
- reject/exception/OOD/timeout 후 accepted-state checksum이 동일해야 한다.
- dense `Q Q^T` projector와 unbounded rank를 금지한다.
- backprop model은 research baseline으로만 유지한다.

## Alternatives considered

- AI가 displacement를 직접 commit: solver gate 우회 때문에 기각.
- inference-only를 no-backprop으로 표기: online update 요구를 충족하지 않아 기각.

## Verification

- no-backprop static/runtime audit
- replay-before-promotion assertion
- rejection/exception/timeout rollback test
- E(3) equivariance와 OOD test

## Rollback / supersession

AI 경로는 feature flag 없이도 완전히 제거 가능해야 하며 제거 후 physics solve 결과가 유지돼야 한다.
