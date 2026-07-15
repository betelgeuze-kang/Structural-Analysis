# HIP FGMRES recurrence launch/fence rolling ordinal audit v1

- 상태: v0.2.41 feature-branch publication contract milestone
- 범위: exact process-local `HipRtcFgmresV2Kernel` owner의 native-call 순서 감사
- Promotion: `contract_only`, 항상 non-promoting
- 권한: detached receipt 단독이 아니라 retained `expected_context`가 있을 때만 provenance를 재검증

## 목적

v0.2.39의 bound-runtime copy audit은 canonical predecessor enqueue 전부터 global
terminal fence까지 Engine-v2가 소유한 세 copy API의 신규 attempt가 `0`인지
검증한다. 그러나 copy counter만으로는 recurrence kernel launch와 세 fence가 실제로
어떤 시간 순서로 호출됐는지 독립적으로 봉인하지 않는다.

이 v1 companion audit은 기존 canonical, sealed, global, transfer-audit receipt의
의미를 변경하지 않고 다음 exact owner 경로에 별도 rolling ordinal을 추가한다.

1. canonical context가 `context_ready`이고 첫 enqueue 전일 때 start snapshot
2. canonical owned8의 `hipMemsetAsync` 8회
3. canonical fixed kernel descriptor 전체와 첫 fence
4. sealed checkpoint fixed 4-launch descriptor와 두 번째 fence
5. global continuation descriptor 전체와 terminal fence
6. completion-export child가 열리기 전 end snapshot과 expected descriptor replay

첫 recurrence kernel launch 전에 8개 memset이 존재하므로 receipt는 이를 별도
`memset` event kind로 보존한다. “첫 launch가 모든 device operation의 첫 호출”이라고
주장하지 않는다.

## 계측 구조

`HipRtcFgmresV2Kernel`마다 private ledger state 하나를 생성하고 compiler-issued
binding witness와 그 exact object identity를 결속한다. Native choke point는 다음
세 곳뿐이다.

- `_checkpoint_memset_zero()` → sealed `hipMemsetAsync`
- `_launch()` → sealed `hipModuleLaunchKernel`
- `_synchronize_checkpoint_stream()` → sealed `hipStreamSynchronize`

Receipt 발행이 가능한 healthy ledger 경로에서 각 호출은 native callable 직전에
operation ordinal을 한 번 증가시키고 attempt event를 rolling SHA-256 head에 fold한다.
반환 뒤에는 같은 ordinal로 다음 disposition 중 하나를 기록한다.

- `success`: exact integer status `0`
- `rejected`: exact integer nonzero status
- `ambiguous`: 예외, `BaseException`, 또는 non-exact status

Ordinal은 native attempt 뒤 실패해도 되돌리지 않는다. Ledger `begin`/`finish`의
ordinary 내부 오류는 ledger를 비가역 poison해 clean receipt 발행만 fail-closed한다.
Companion audit은 기존 solver 의미를 바꾸지 않으므로 이때 valid memset/launch와
safety fence는 ticket 없는 degraded mode로 계속된다. Invalid descriptor는 native 전
거부하고, enqueue ledger-begin의 `BaseException`은 pending을 rollback한 뒤 전파한다.
Fence-begin `BaseException`은 exact native safety fence 성공 뒤 전파하며, native fence
실패·non-exact·rejection이 있으면 그 authoritative native 결과를 우선한다.
Event 배열은 저장하지 않고 고정 counter, 마지막 완료 event, rolling head만 유지하므로
event당 추가 상태는 `O(1)`, 전체 host-control 계측 시간은 `O(L+K)`, ledger 메모리는
`O(1)`이다. 이는 유한요소 해석 전체의 `O(N)` 증거가 아니다.

Descriptor는 raw pointer를 포함하지 않는다. Canonical/sealed/global fixed schedule의
공통 semantic row projection을 canonical SHA-256으로 만들고, memset은 role과 exact
byte length를 결속한다. Auditor는 retained full partition에서 다음 순서를 다시 만든다.

```text
memset × 8
→ canonical launches
→ fence
→ sealed checkpoint launches × 4
→ fence
→ global continuation launches
→ terminal fence
```

Start rolling head에서 이 expected successful event chain을 다시 fold한 값이 exact
kernel end head와 같아야 한다. 추가·누락·재정렬 event, rejected/ambiguous/in-flight
call, binding drift, 다른 kernel/token/runtime/device/stream lineage는 receipt 발행을
거부한다.

## Ordinal 계약

Start operation ordinal을 `b`, canonical launch 수를 `C`, continuation launch 수를
`G`, full program launch 수를 `L=C+4+G`라 두면 clean path는 다음과 같다.

- 첫 recurrence launch: `b + 9`
- canonical fence: `b + 9 + C`
- sealed checkpoint fence: `b + 14 + C`
- terminal fence: `b + 8 + L + 3`
- 전체 native-call delta: `8 + L + 3`
- event-sequence delta: `2(8 + L + 3)`

끝 snapshot의 마지막 완료 event는 반드시 `fence/success`이고 in-flight는 `0`이다.
`hipStreamQuery`로 ambiguous sync를 회복한 lifecycle 경로는 clean successful fence로
재분류하지 않으므로 이 성공 receipt를 발행할 수 없다.

## True claim

- exact process-local FGMRES-v2 kernel ledger와 retained context 결속
- clean-receipt 경로의 native-call 전 attempt 및 반환/중단 disposition 보존
- fixed 8 memset, full recurrence descriptor, 세 fence의 exact 순서 replay
- canonical→sealed→global의 same kernel, loaded runtime, checkpoint token, device,
  stream lineage
- terminal fence가 마지막 package-owned ledger event임
- completion-export child open 전 seal boundary
- constant-space rolling ledger 구현

## 계속 false인 claim

- raw CDLL, fresh bind, `dlsym`, C extension, third-party launch 관찰
- process-wide ROCm launch 또는 모든 device operation 완전성
- hostile same-process Python mutation 저항
- GPU kernel의 의미론적 실행 성공, device content, terminal outcome, solution, parity
- detached receipt 단독 provenance 또는 cryptographic authenticity
- broad iteration-host-copy-zero
- actual external `gfx1100`, signed hardware truth, ResultIR
- end-to-end `O(N)`, speedup, promotion eligibility, commercial readiness

## 현재 검증

- focused audit 회귀: `11 passed in 242.95s (0:04:02)`
- public API/capability 회귀: `16 passed in 1.73s`
- RTC 전체 회귀: `134 passed in 43.82s`
- current-snapshot actual local `gfx1030` required gate: `1 passed in 37.22s`
  - owned memset `8/8`, full-program launch attempt/success exact 일치, fence `3/3`
  - ordinal audit과 transfer audit을 같은 solve/export lineage에서 검증했다.
  - 이 결과는 현재 작업 세션의 비영속 관찰이며 standalone signed hardware receipt나
    외부 실행 로그가 아니다.
- exact 10-slot family composition: v0.2.42 additive
  [audited parity v2](engine-v2-hip-fgmres-model-family-audited-parity-v2.md)에
  결합 완료
  - identity-token 패치 전 source gate `1 passed in 3171.31s (0:52:51)`;
    token-hardened current-source gate pending
  - 10-slot owned memset `80/80/0/0/0`, launch `1,230/1,230/0/0/0`,
    fence `30/30/0/0/0`
  - unsigned 비영속 작업 세션 관찰이며 standalone provenance는 아님

## 다음 단계

1. **완료(v0.2.42):** 기존 10-slot loop에 per-kernel ordinal result를 결합하되
   device solve/export를 중복 실행하지 않는다.
2. **완료(v0.2.42):** 별도 audited-parity v2가 세 retained authority를 재생하고
   parity, host-transfer audit, ordinal audit receipt hash와 공통 lineage를 함께
   결속한다. 이 결과만으로 broad iteration-host-copy-zero를 승격하지 않으며 detached
   소비 경로에는 authority들을 묶는 서명 envelope가 추가로 필요하다.
3. Exact fence-prefix consume seal, post-fence enqueue 차단, query-recovery seal은 이
   관측형 v1보다 강한 후속 lifecycle 계약으로 분리한다.
