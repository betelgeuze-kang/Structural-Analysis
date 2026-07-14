# Engine v2 HIP FGMRES fixed-suite model-family parity v1

## 목적

이 계약은 exact process-local
`HipFgmresModelCaseParityResultV1`을 package-owned 고정 모델군 행렬에 집계한다.
호출자는 family/slot label이나 required architecture를 전달할 수 없다.

v1 행렬은 다음 10개 target slot과 두 architecture base로 고정된다.

- frame: axial, weak-axis bending, strong-axis bending, torsion
- frame: rotated local axis, serial later-column
- truss: axial
- recurrence: initial/early terminal
- recurrence: later restart/partial final cycle
- recurrence: exact full final cycle/final guard
- architecture: `gfx1030`, `gfx1100`

따라서 전체 행렬은 20개 cell이다.

## authoritative 분류

각 입력 case result는 먼저 단일-case validator로 전체 replay한다. 그 뒤 보존된
`ExecutionPlanV2._source_buffers`에서 다음을 파생한다.

- element type/formulation/material law/section family 조합과 수량
- connectivity, coordinates, local-axis roll, offset, release
- support, prescribed value 및 selected load metadata
- ModelIR, solver buffer, operator, numeric, symbolic, partition hash
- node/element/global/free DOF 및 reduced CSR nnz
- CPU status/termination과 policy/result hash

파생 descriptor가 package source에 등록된 하나의 exact slot hash와 유일하게
일치해야만 coverage cell로 계산한다. UUID, PCI BDF, device ordinal 또는
architecture feature suffix는 ISA 수를 늘리지 않으며, matrix key는 normalized
runtime architecture base만 사용한다. 같은 `(slot, architecture base)`의 중복은
silent dedup하지 않고 거부한다.

## 현재 상태

v1은 10개 target slot의 의미와 행렬을 고정했지만 exact golden fixture hash는
아직 하나도 등록하지 않았다. 따라서 임의의 실제 case를 slot으로 세지 않으며,
빈 입력을 포함한 현재 authoritative status는 다음과 같다.

```text
status = pending_model_cases_and_external_architecture
required slots = 10
registered slots = 0
required cells = 20
covered cells = 0
missing cells = 20
```

현재 구현은 full model-family parity나 multi-architecture parity를 완료한 것이
아니다. 다음 단계는 package-owned fixture를 하나씩 고정하고 실제 `gfx1030` lane
전체를 채운 뒤, 독립 `gfx1100` runner에서 같은 suite를 실행하는 것이다.

## claim boundary

현재 true인 항목은 고정 manifest 결속, authoritative metadata 분류 규칙,
submitted exact result replay, normalized architecture-base key 및 duplicate-cell
거부뿐이다.

다음은 항상 false다.

- fixed-suite registration/matrix completion
- full model-family 및 multi-architecture parity
- same-process actual two-ISA verification
- serialized receipt authority 또는 unsigned external evidence 사용
- signed promotion
- iteration host-copy zero
- product solution/ResultIR readiness
- performance, speedup, `O(N)` 및 commercial readiness

직렬화 receipt는 구조와 canonical hash만 검증한다. process-local source authority를
복원하지 않으며 missing cell을 채울 수 없다.

## 검증

2026-07-14 기준:

- model-family unit/adversarial: `16 passed`
- model-family + single-case parity 인접: `37 passed`
- public API/package resource: `3 passed`
- capability/device/case/family/public/RTC 집중 회귀: `214 passed in 40.59s`
- actual RX 6900 XT `gfx1030` single-case→family process-local replay:
  `1 passed in 141.24s`
- detached validated receipt/CPU snapshot TOCTOU 방어와 UUID·PCI↔architecture
  base 충돌 거부 독립 재감사: 잔여 BLOCKER/HIGH/MEDIUM/LOW 없음
- wheel `964176` bytes, SHA-256
  `99ea00c0b390a7c056e2e1f8fd730be06596d12a51348f3e971299500f98399b`;
  격리 설치에서 public API·3 schema·FGMRES HIP kernel resource import 통과
- Ruff, py_compile, strict Draft 2020-12 schema, whitespace: 통과

두 architecture lane을 cross-process로 합치는 서명·trust-anchor promotion envelope는
별도 v2 계약으로 구현해야 한다. v1 local matrix는 모든 cell이 채워지더라도
unsigned/non-promoting으로 유지한다.
