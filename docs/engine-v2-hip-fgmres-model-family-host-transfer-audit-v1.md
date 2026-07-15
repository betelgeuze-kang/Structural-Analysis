# Engine v2 HIP FGMRES model-family host-transfer audit v1

## 상태

- 버전: v0.2.40
- 구현: `implemented`
- 승격: `contract_only`, `promotion_eligible=false`
- 범위: package registry의 exact `gfx1030` 10-slot family-v2 결과와 각
  `context.result` 캡처 순간에 `exported`인 slot별 bound-runtime transfer-audit
  authority의 process-local composition
- actual 10-slot 결합 hardware 영수증: 최종 트리 재실행 중, 완료 전까지 pending
- external actual `gfx1100`: `0/10`

## 목적

v0.2.39는 단일 canonical→sealed→global recurrence 창에서 exact bound runtime의
신규 copy API attempt가 0이고 terminal fence 뒤 completion export가 blocking D2H
3회라는 사실을 검증한다. v0.2.32 family-v2는 package registry의 `gfx1030` 10개
고정 slot 수치 parity를 검증하지만 historical receipt의
`iteration_host_copy_zero_verified`는 false다.

v0.2.40은 두 기존 계약을 변경하지 않고 별도 composition receipt에서 결합한다.
각 model-case parity result와 audit result가 동일한 completion-export context/result
객체를 사용했는지 확인한다. Composition factory 자체는 solve/export API를
호출하지 않고 이 retained export identity만 소비한다. 이는 전체 프로세스에
관계없는 추가 solve/export가 없었음을 동적으로 증명하지는 않는다.

## Authority 경계

공개 factory는 다음 process-local 입력만 받는다. Mint 시 각 audit context는
해당 `context.result`를 읽는 순간에 반드시 `exported`여야 한다. 모든 context의
동시 liveness나 aggregate lock은 주장하지 않는다.

```python
result = attest_hip_fgmres_model_family_host_transfer_audit_v1(
    family_result,
    tuple(audit_contexts),
)
```

Factory는 각 audit context의 현재 result를 캡처하고
`validate_hip_fgmres_iteration_host_transfer_audit_result_v1(...,
expected_context=context)`로 재검증한다. Audit result만 받지 않는 이유는 서명이나
expected context 없는 detached audit receipt가 provenance authority가 아니기 때문이다.

각 slot에서 다음 객체 identity가 반드시 같다.

```python
case._observation_result._source_export_context \
    is audit_result.completion_export_context
case._observation_result._source_export_result \
    is audit_result.completion_export_result
```

그 뒤 completion export context/receipt/payload, global context/receipt, recurrence plan,
kernel identity/source, compiled architecture, device ordinal, free DOF `F`, maximum
restart count `R`을 case와 audit 양쪽에서 교차 검증한다. Caller 순서는 신뢰하지 않고
family-v2의 canonical registry slot 순서로 다시 정렬한다.

Authoritative result는 family result와 10개 `(audit context, captured result)`를 strong
retain한다. Mint에는 각 authority를 각각의 `context.result` read 순간에
`exported` 상태에서 캡처하지만, 후속 result
재검증은 upstream expected-context 계약에 따라 이미 캡처한 `closed` publication도
재생할 수 있다. 따라서 claim은 현재 liveness가 아니라 캡처 시점의 exported
상태를 뜻한다. Serialized receipt는 구조·hash 일관성 projection일 뿐 standalone
provenance가 아니다.

## 고정 영수증

Receipt는 exact `gfx1030` 10-slot만 받는다. Partial family, `gfx1100`, 20-cell unsigned
matrix, 9/11개 context는 fail-closed한다.

Slot별 조건:

- recurrence-program copy API attempt/sequence delta `0`
- completion-export sequence delta `6`
- blocking D2H attempt/success/failure `3/3/0`
- byte 수 `16F + 192 + 72R`
- native loader-bound runtime 및 exact runtime scope

현재 package registry의 합계:

- paired slots `10`
- source family matrix `10/20`, missing `gfx1100` `10`
- recurrence copy attempts `0`
- blocking D2H attempt/success/failure `30/30/0`
- completion export bytes `4,408`

각 slot은 별도 runtime/stream owner를 사용할 수 있다. 합계는 10개 receipt의 산술
합이며 하나의 process-wide ordinal ledger나 동일 stream을 뜻하지 않는다.

## True claim

- fixed package registry와 exact source family-v2 receipt 결속
- exact registered `gfx1030` 10-slot coverage 결속
- 같은 프로세스의 10개 audit authority 각각을 `context.result` read 순간에
  `exported` 상태에서 캡처; 10개의 동시 liveness는 비주장
- case parity와 audit의 same completion-export object identity 결속
- case/audit completion/global/recurrence/kernel/device/F/R 교차 결속
- slot별 정의된 recurrence 창의 bound-runtime copy API attempt 0
- slot별 terminal fence 뒤 blocking D2H 정확히 3회
- composition factory가 solve/export API 호출 없이 retained export identity만 재사용

## 명시적 비주장

다음은 모두 false다.

- external actual `gfx1100` 또는 unsigned two-architecture audited suite
- process-wide ROCm activity/host-transfer/DMA 0
- 창 시작 전에 반환한 async copy의 device completion 0
- raw CDLL/fresh binding, ctypes/dlsym/C extension, third-party transfer 0
- setup/source apply/teardown/case 사이 transfer 0
- 모든 case가 동일 runtime/stream을 공유함
- 전체 프로세스의 관계없는 추가 device solve/export 부재
- broad `iteration_host_copy_zero_proven`
- full model-family 또는 일반 multiarchitecture parity
- standalone receipt provenance authenticity, signed evidence/promotion
- ResultIR, speedup, end-to-end O(N), commercial readiness

## Hardware loop 통합

공유 hardware helper는 canonical context 생성 직후와 첫 predecessor enqueue 사이에
선택적 `before_canonical_enqueue` hook을 제공한다. Family hardware test는 hook에서 audit을
열고 작성된 family helper control flow에서 canonical→sealed→global recurrence를 한 번
실행한다. Global fence 뒤 direct
completion exporter를 별도로 열지 않고 audit exporter 결과를 terminal observer와
model-case parity에 그대로 사용한다. 이 정적 control-flow 사실과 exact object
identity 결속은 composition factory 밖 전체 프로세스의 no-extra-solve 증거가 아니다.

Cleanup 순서는 audit → global → sealed → canonical/live parent chain이다. Audit close가
내부 exporter child와 runtime owner reservation을 해제한다.

## 검증 계획

현재 트리의 synthetic/public/capability 검증은 `24 passed`, 인접
historical family-v2/audit-v1 두 파일은 `21 passed`다. Actual 수치는 재실행이 완료되기 전에
성공으로 기록하지 않는다.

- exact 10-slot 합성 authority composition과 caller 역순 canonicalization
- missing/duplicate/foreign expected context 거부
- export object identity, kernel/lineage binding 위조 거부
- source family/composition registry cross-snapshot 거부
- detached claim/order/pair-hash/exact-type 및 duplicate context/device-kernel 위조 거부
- valid payload의 top-level 및 모든 nested object strict schema
- public `__all__` identity와 package schema resource
- 기존 family-v2/audit-v1/helper 인접 회귀
- 기존 actual `gfx1030` 10-slot hardware loop 한 번에서 family `10/20`, recurrence
  attempts `0`, export `30/30/0`, `4,408` bytes 확인
