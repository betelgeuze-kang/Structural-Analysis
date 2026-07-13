# ModelIR v2 Phase 0 Contract

- Schema: [`src/structural_analysis/schemas/model_ir_v2.schema.json`](../src/structural_analysis/schemas/model_ir_v2.schema.json)
- Validator: [`src/structural_analysis/model_ir/validation.py`](../src/structural_analysis/model_ir/validation.py)
- Golden fixture: [`tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json`](../tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json)
- Authority: [ADR-002](adr/002-modelir-stateir-resultir-schema.md)

## Phase 0 boundary

이 계약은 v1 `CanonicalModel`을 즉시 교체하지 않는다. Engine v2 adapter와 CPU/HIP operator가 공유할 엄격한 입력 의미론을 먼저 고정한다.

현재 capability profile은 `engine_v2_phase0_linear_3d` 하나다. Schema가 frame/truss 의미를 표현하더라도 새 v2 solver capability가 검증됐다는 뜻은 아니다.

## Validation layers

1. JSON Schema draft 2020-12
2. ID/index/reference 및 구조공학 invariant
3. blocking unsupported feature에 따른 analysis-readiness
4. 후속 solver preflight와 operator parity

Schema-valid과 analysis-ready는 분리한다. `unsupported_features[].blocking=true`인 문서는 보존·검토할 수 있지만 실행 준비 상태로 승격할 수 없다.

## Canonical rules

- SI 단위: `m`, `N`, `kg`, `s`, `rad`
- 노드당 DOF order: `UX, UY, UZ, RX, RY, RZ`
- residual sign: `F_int - F_ext`
- entity array index는 0부터 연속이며 배열 순서와 동일
- unknown field는 거부하고 확장은 namespaced `extensions`에만 기록
- `NaN`, Infinity, dangling reference, duplicate ID/index, zero effective length, load-combination cycle은 거부
- canonical serialization은 key sort, compact separators, UTF-8, signed-zero normalization을 사용

## HIP-safe separation

ModelIR에는 불변 구조·재료·하중·constraint와 source provenance만 둔다. 다음 항목은 ModelIR 작성자가 선언하지 않고 별도 계약이 생성한다.

- dtype, shape, layout, column order, numerical hash: `SolverModelBuffers v1`
- DOF map, vector space, operator graph, tolerance, placement/residency: `ExecutionPlan`
- trial/committed kinematic 및 constitutive 값: `StateIR`
- device pointer, HIP stream, device ordinal, allocator: `DeviceExecutionContext`

이 분리는 ModelIR 설명과 실제 backend 입력이 서로 다른 이중 진실이 되는 것을 막는다.

## SolverModelBuffers v1

[`src/structural_analysis/engine_v2/buffers.py`](../src/structural_analysis/engine_v2/buffers.py)가 validated ModelIR과 선택 load pattern으로부터 read-only bytes-backed little-endian buffer를 생성한다.

- 모든 index array는 zero-based `<i4`
- numerical buffer hash와 ModelIR document hash를 분리
- ordered entity ID mapping hash 별도 기록
- element/material/section code table과 component별 단위/열 순서를 manifest에 기록
- release, prescribed value, self-weight, combination/time/stage 등 현재 CPU-compatible profile 밖의 기능은 fail-closed
- CPU와 HIP는 같은 `numeric_buffer_hash`를 결과 receipt에 기록해야 함

## Implemented companion contracts

- [MGT → ModelIR v2 Phase 0 adapter](mgt-modelir-v2-phase0-adapter.md): lossless source ledger, strict MGT 9.3.0 linear-frame subset, SI normalization, semantic reverse projection
- deterministic `SolverModelBuffers v1` packer와 ABI/hash snapshot
- FP64 6DOF frame/linear-truss CPU reference, analytic/dense-sparse/JVP 검증
- [ExecutionPlan·StateIR·ResultIR v1](engine-v2-execution-state-result-contracts-v1.md): compiled DOF/CSR/recovery operator, immutable trial lifecycle, full numerical receipt chain
- [HIP DeviceExecutionContext v1](engine-v2-hip-context-v1.md): 전체 SolverModelBuffers의 persistent device allocation과 explicit transfer telemetry; operator/solver 미결합
- [Fixed-rank projection v1](engine-v2-fixed-rank-projection-v1.md): ExecutionPlan-bound bounded implicit projection primitive
- [AI proposal·physics gate·QR memory v1](engine-v2-ai-proposal-gate-qr-v1.md): immutable `DQy` overlay, CPU full-physics replay, exact rollback, non-consuming shadow parity, solver-approved bounded teacher memory; calibrated OOD/warm-start/RLS learning은 미구현

## Next implementation slice

- v1 `CanonicalModel` → v2 explicit migration report
- 같은 buffer hash를 사용하는 CPU/HIP residual/JVP parity
- calibrated OOD/UQ와 proposal을 실제 소비하는 iterative solver warm-start
- solver-approved QR memory 위 local RLS/Kalman/readout update
- frame offset/release 및 shell reference operator
