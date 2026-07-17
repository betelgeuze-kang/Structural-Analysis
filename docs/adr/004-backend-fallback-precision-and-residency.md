# ADR-004: Backend, Fallback, Precision, and Residency

- Status: accepted
- Date: 2026-07-10
- Deciders: Engine v2 architecture baseline

## Context

현재 일부 GPU 경로는 matvec 또는 residual 일부만 장치에서 수행하고 host solve/fallback을 포함한다. 단순 `device_residency_ratio` 값으로는 실제 장치 상주를 증명하기 어렵다.

## Decision

- backend 역할을 `cpu_reference`, `cpu_optimized`, `hip`으로 분리한다.
- placement policy는 vendor 이름보다 필요한 기능(`fp64`, sparse f64, device reduction 등)으로 기술한다.
- fallback은 `forbidden` 또는 `explicit`만 허용하며 자동/숨은 fallback은 금지한다.
- verification mode는 deterministic FP64, performance mode는 승인된 mixed precision을 사용한다.
- HIP production solve는 모델/operator/state/Krylov basis를 장치에 유지하고 iteration scalar만 host에 보낸다.
- receipt는 H2D/D2H bytes, sync count, kernel/operator timing, peak memory, precision, hardware를 기록한다.

## Normative invariants

- HIP PASS는 CPU fallback 0과 iteration당 state/residual host copy 0을 요구한다.
- 작은 모델에서 CPU가 빠른 경우 size-aware 선택을 허용하되 선택 이유를 기록한다.
- mixed precision 결과는 FP64 residual/energy replay와 iterative refinement gate를 통과한다.
- 하드코딩된 단일 GPU architecture를 production 계약으로 사용하지 않는다.

## Alternatives considered

- GPU SpMV + CPU Krylov를 HIP solver로 표기: residency claim이 부정확해 기각.
- GPU 실패 시 묵시적 CPU 재실행: 운영상 원인 은닉 때문에 기각.

## Verification

- transfer/sync instrumentation
- cold/warm hardware benchmark
- deterministic/performance parity
- fallback failure injection

## Rollback / supersession

HIP gate 실패 시 explicit CPU backend로 재계획할 수 있지만 HIP 성공 receipt로 승격하지 않는다.
