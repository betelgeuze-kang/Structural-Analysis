# Engine v2 HIP FGMRES bound-runtime host-transfer audit v1

## 상태

- 버전: v0.2.39
- 구현: `implemented`
- 승격: `contract_only`, `promotion_eligible=false`
- 현재 성공 증거: test-double, actual local `gfx1030` single case, v0.2.40
  exact 10-slot family/audit composition
- 장치 표기 경계: 영수증과 hardware gate는 ISA `gfx1030`을 결속한다. RX 6900 XT는
  운영자 관찰값이며 이 계약이 독립적으로 결속하는 device marketing model이 아니다.
- actual local `gfx1030` 10-case composition: `1 passed in 2004.37s (0:33:24)`,
  recurrence attempt `0`, export `30/30/0`, `4,408` bytes
- 실제 external `gfx1100`: `0/10`; 별도 영속 hardware receipt/log는 미확보

## 목적과 정확한 경계

이 계약은 FGMRES가 장치에 상주한 뒤 반복 프로그램을 실행하는 동안 Engine-v2가
소유한 exact bound HIP runtime의 세 copy API를 통한 신규 attempt가 없었는지
검증한다. 실제 장치 DMA activity 전체를 추적하는 계약은 아니다.

감사 창은 다음 순서로 고정된다.

1. canonical predecessor context가 `context_ready`이고 첫 enqueue 전일 때 시작
2. canonical predecessor 전체 enqueue와 fence
3. sealed checkpoint transaction 전체 enqueue와 fence
4. global recurrence continuation 전체 enqueue와 terminal fence
5. terminal fence 뒤 별도 phase에서 completion exporter 실행
6. `solution_x`, `true_residual`, `solve_record`의 blocking D2H 3회 완료 뒤 종료

첫 번째 phase는 H2D async, D2H async, blocking D2H의 attempt/success/failure/byte
delta가 모두 0이어야 한다. 두 번째 phase는 async copy 0, blocking D2H attempt와
success가 정확히 3, failure 0, 총 byte가 `16F + 192 + 72R`이어야 한다.

## 계측 구조

`_BoundHipContextRuntime`은 생성 시 하나의 private monotonic copy ledger를 만든다.
`copy_h2d_async`, `copy_d2h_async`, `_BoundBlockingD2HCopy`가 같은 ledger를 공유한다.
각 copy는 native callable을 호출하기 전에 attempt와 byte를 기록하고, 반환 또는
예외 뒤 success/failure를 닫는다. 그러므로 실패한 copy나 Python 예외도 0-copy
주장에 숨을 수 없다. Snapshot 시 in-flight API invocation이 있거나 counter가 감소하거나
runtime/counter/copy-binding identity가 바뀌면 성공 영수증은 발행되지 않는다.
여기서 in-flight는 Python/native API 호출이 아직 반환되지 않은 상태만 뜻한다.
창 시작 전에 성공 반환한 `hipMemcpyAsync`가 장치에서 아직 완료되지 않았는지는
관찰하지 않는다.

상위 `HipFgmresIterationHostTransferAuditExecutionContextV1`은 canonical open 시
start snapshot을 고정한다. Global completion capability와 exact canonical→sealed→global
lineage를 재검증한 뒤 fence snapshot을 잡고 zero delta를 검사한다. 그 다음 기존
completion exporter를 직접 열어 결과를 만든 뒤 export snapshot을 잡는다. 기존
global/export receipt의 역사적 hash와 false claim은 변경하지 않고 새 audit receipt가
두 source receipt hash와 payload hash를 결속한다.

## 공개 API

```python
opened = open_hip_fgmres_iteration_host_transfer_audit_v1(canonical_context)

# 기존 canonical → sealed → global 실행

audit_result = opened.context.export_completion_buffers(
    global_context,
    completion_capability,
)
```

`audit_result`는 새 audit receipt와 기존 completion export context/result를 함께
보존한다. Terminal observation 같은 기존 후속 process-local consumer에는 audit
wrapper 자체가 아니라 `audit_result.completion_export_context`와
`audit_result.completion_export_result`를 각각 꺼내 전달한다. 후속 소비가 끝난 뒤
audit context를 `close()`하면 exporter child lease도 닫힌다.

## True claim

- exact canonical→sealed→global lineage 결속
- exact bound runtime copy counter 결속
- 정의된 recurrence-program 창의 bound-runtime copy attempt 0
- terminal fence 뒤 blocking D2H 정확히 3회
- completion export 정확한 byte 수
- 동일 runtime/device/stream lineage

## 명시적 비주장

다음은 모두 false다.

- process-wide ROCm activity 또는 외부 DMA 부재
- 창 시작 전에 enqueue되어 API가 반환한 async copy의 완료 또는 device DMA activity 0
- `LoadedHipRuntime.cdll` compatibility view와 fresh `bind()` 호출 부재
- direct ctypes/dlsym, C extension, third-party ROCm 호출 부재
- hostile same-process monkeypatch/interposition 배제
- synchronization 또는 host scheduling 0
- solver setup·initial source apply transfer 0
- 전체 solver/iteration host-copy-zero
- `expected_context` 또는 서명 없는 standalone receipt의 provenance authenticity
- numerical parity, solution-ready, ResultIR
- O(N), 성능 우위, 상용 준비, promotion eligibility

이 구분 때문에 capability의 true 필드는
`recurrence_program_bound_runtime_copy_attempt_zero`이며 broad
`iteration_host_copy_zero_proven`은 계속 false다.

## 검증

- bound runtime H2D/D2H async와 blocking D2H 각각의 성공·native error·예외 accounting
- start snapshot 중 reentrant predecessor enqueue를 원자적 경계 재검사로 거부
- test-double canonical→sealed→global zero-copy 정상 경로
- post-fence export 3-copy/6-event/exact-byte 검증
- window 내부 실패 D2H attempt 주입 시 proof 미발행
- detached receipt rehash로 broad claim을 true로 올리는 공격 거부
- 실제 valid payload의 top-level/nested strict Draft 2020-12 unknown property 거부
- exact numeric/string type alias, exporter backend/binding 위조, cached foreign input 거부
- public export와 package schema resource 무결성
- package Python source의 literal/constant-folded `hipMemcpy*` bind 및 private
  `_memcpy*` invocation owner를 AST 휴리스틱으로 `context.py` 하나에 제한
- 기존 HIP context `12 passed`
- 기존 completion export `11 passed`
- 작업 세션 actual local `gfx1030` single case `1 passed in 36.34s`
  - canonical→sealed→global recurrence copy event delta `0`
  - post-fence blocking D2H `3`회, `360` bytes
  - loader-issued native bound runtime 확인
  - 이 시간과 pass 수는 별도 영속 receipt/log가 아닌 현재 작업 세션 관찰값

AST allowlist는 package-owned Python 경로의 우발적 우회를 잡는 회귀 가드다. 동적 symbol
구성, raw CDLL/fresh binding, ctypes/dlsym/C extension, 외부 라이브러리까지 부재함을
증명하는 정적 완전성 검사는 아니다.

## 다음 단계

1. **완료(v0.2.40):** 기존 10-slot model-family hardware loop에 audit을 결합해
   slot당 recurrence 0, export 3을 한 loop에서 검증했다. GPU recurrence/export는
   중복하지 않았지만 반복 live family validation으로 전체 gate는 `33:24`가
   걸렸으며 이 CPU/control-plane 재검증 비용은 후속 최적화 대상이다.
2. **완료(v0.2.41):** additive [RTC launch/fence rolling ordinal audit](engine-v2-hip-fgmres-recurrence-launch-fence-audit-v1.md)을
   추가해 canonical pre-enqueue부터 terminal fence 직후까지 fixed memset/launch/fence
   descriptor의 시간 순서를 독립 rolling chain으로 봉인했다.
3. 다음 audited parity v2가 parity receipt hash, 이 transfer-audit receipt hash,
   ordinal-audit receipt hash를 함께 소비한 뒤에만 좁은 iteration-host-copy claim
   승격을 검토한다.
