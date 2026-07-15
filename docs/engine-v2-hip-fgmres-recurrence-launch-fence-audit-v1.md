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

각 호출은 native callable 직전에 operation ordinal을 한 번 증가시키고 attempt
event를 rolling SHA-256 head에 fold한다. 반환 뒤에는 같은 ordinal로 다음 disposition
중 하나를 기록한다.

- `success`: exact integer status `0`
- `rejected`: exact integer nonzero status
- `ambiguous`: 예외, `BaseException`, 또는 non-exact status

Ordinal은 실패해도 되돌리지 않는다. 동시에 둘 이상의 in-flight native call은
kernel 내부 ledger가 pre-native fail-closed한다. Event 배열은 저장하지 않고
고정 counter, 마지막 완료 event, rolling head만 유지하므로 event당 추가 상태는
`O(1)`, 전체 host-control 계측 시간은 `O(L+K)`, ledger 메모리는 `O(1)`이다. 이는
유한요소 해석 전체의 `O(N)` 증거가 아니다.

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
- native-call 전 attempt 및 반환/중단 disposition 보존
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

- 신규 focused/public/capability 회귀: `22 passed in 154.71s`
- actual local `gfx1030` single-case required gate: `1 passed in 37.24s`
  - owned memset `8/8`, full-program launch attempt/success exact 일치, fence `3/3`
  - ordinal audit을 terminal fence 뒤 seal하고 기존 transfer-audit exporter보다 먼저 검증
- 위 actual 결과는 이 작업 세션의 비영속 관찰이며 standalone signed hardware
  receipt 또는 외부 실행 로그가 아니다.
- exact 10-slot family composition: 다음 additive audited-parity 단계로 보류

## 다음 단계

1. 기존 10-slot loop에 per-kernel ordinal result를 결합하되 device solve/export를
   중복 실행하지 않는다.
2. parity receipt hash, host-transfer audit hash, ordinal audit hash를 함께 소비하는
   별도 audited-parity v2에서만 좁은 iteration-host-copy claim 승격을 검토한다.
3. Exact fence-prefix consume seal, post-fence enqueue 차단, query-recovery seal은 이
   관측형 v1보다 강한 후속 lifecycle 계약으로 분리한다.
