# Engine v2 HIP FGMRES model-family audited parity v2

## 판정

`v0.2.42` 후보 계약은 package fixture registry의 exact `gfx1030` 10-slot 고정
suite에 대해 다음 세 retained authority를 한 process-local receipt로 결속한다.
Contract/test-double 구현은 identity-token-hardened current source에서 통과했다.
비재사용 identity token 패치 전 source snapshot은 actual local `gfx1030` 10-slot
required hardware gate를 통과했다. Current-source actual local 통합 gate도 CPU fallback
없이 `1 passed in 7820.35s (2:10:20)`로 통과했다. 두 actual 결과는 비영속 unsigned
관찰이며 standalone provenance나 promotion 증거가 아니다.

1. model-case CPU/HIP numerical parity를 보유한 family-v2 result
2. canonical enqueue부터 terminal fence까지 bound-runtime copy attempt가 `0`이고
   fence 뒤 completion export가 정확히 세 번의 blocking D2H를 사용한 transfer
   audit result
3. package-owned RTC kernel의 owned memset, fixed recurrence launch descriptor,
   canonical/sealed/global fence 순서를 rolling ordinal chain으로 재생한
   launch/fence audit result

구현은 additive다. 기존 family-v2, transfer-audit-v1,
launch/fence-audit-v1 receipt나 수치 solver를 변경하지 않는다. 신규 factory의 고정된
direct-call surface는 solver, completion export, ordinal seal 또는 native ROCm
entrypoint를 포함하지 않고 이미 retained된 authority의 validator만 재생한다.

## 단일 실행 경계

기존 `gfx1030` 10-slot hardware test harness를 slot마다 다음 순서가 되도록 확장했고,
identity-token 패치 전 source snapshot과 current source의 actual 통합 실행으로 검증했다.

```text
canonical context ready
  -> transfer audit open
  -> launch/fence audit open
  -> canonical predecessor enqueue + fence
  -> sealed checkpoint enqueue + fence
  -> global continuation enqueue + terminal fence
  -> launch/fence audit seal
  -> existing transfer-owned completion export exactly once
  -> terminal observation -> model-case parity
```

두 audit은 canonical predecessor의 첫 enqueue 전에 열린다. Ordinal audit은 global
terminal fence 직후이면서 completion-export child가 열리기 전에 seal된다. 동일한
transfer-owned export context/result 객체가 terminal observation과 model-case parity에
그대로 전달되도록 wiring했다. Harness 구조상 slot당 device recurrence와 completion
export 호출은 각각 한 번이다. 패치 전 source의 required gate가 이 wiring을 CPU
fallback 없이 actual local `gfx1030`에서 통과했고, token-hardened current-source gate도
동일 wiring과 exact 합계를 통과했다.

## 결속 계약

신규 composition은 source host-transfer result를 먼저 authoritative result validator로
재생한다. 이 재생이 retained family case, terminal observation, completion export
context/result의 객체 동일성을 보존해야 한다. 이어서 10개 ordinal result를 각각
`expected_context`로 검증한 다음 다음 공통 lineage를 exact equality로 교차검증한다.

- canonical context ID와 open/fenced receipt hash
- sealed-checkpoint context ID와 receipt hash
- global context ID, global/completion receipt hash
- recurrence plan, recurrence-kernel ABI, combined ABI
- kernel identity와 source SHA-256
- full/prefix/continuation schedule, direct-generation, physical-projection hash
- registry에서 재계산한 recurrence/combined ABI, kernel source, canonical/checkpoint
  schedule 및 전체 operation program descriptor hash
- compiled architecture와 device ordinal
- free DOF, maximum restart, fixed full-program launch count

Caller가 ordinal contexts를 어떤 순서로 넘겨도 receipt observation은 package registry의
10개 slot 순서로 canonicalize된다. Context/result/global/slot의 누락, 중복, foreign
authority, cross-run splice는 fail-closed한다.

## 정확한 합계

고정 suite receipt는 다음 합계를 요구한다.

| 항목 | exact 값 |
|---|---:|
| required/paired local slots | `10/10` |
| covered/expected matrix cells | `10/20` |
| missing `gfx1100` cells | `10` |
| recurrence bound-runtime copy attempts | `0` |
| completion blocking D2H attempt/success/failure | `30/30/0` |
| completion export bytes | `4,408` |
| owned memset attempt/success/rejected/ambiguous/in-flight | `80/80/0/0/0` |
| terminal-chain fence attempt/success/rejected/ambiguous/in-flight | `30/30/0/0/0` |
| launch attempt/success | `1,230/1,230` |
| launch rejected/ambiguous/in-flight | `0/0/0` |

각 slot의 `operation_delta`는 `8 + full_launch_count + 3`, `event_delta`는 그
두 배여야 한다. 이 합계는 package-owned rolling ledger와 exact bound runtime에만
적용된다.

## 복잡도 경계

Slot 수를 `S`, slot별 retained ordinal descriptor 수를 `L_i`라 하면 registry/global/
transfer join은 hash map을 사용해 `O(S)`, 하위 ordinal authority 재생을 포함한
전체 composition 검증은 `O(S + sum(L_i))`다. Receipt 상태는 event array가 아닌
slot별 고정 projection이므로 `O(S)`이고 현재 `S=10`으로 고정된다. 이는
composition control-plane 계약이지 FE solver의 end-to-end `O(N)` 증거가 아니다.

## 명시적 claim boundary

이 단계의 retained-authority receipt가 실제로 발행된 실행에서 참으로
만드는 주장은 다음 한 문장으로 제한한다.

> Exact package `gfx1030` 10-slot fixed suite에서 retained numerical parity,
> bound-runtime recurrence copy-attempt-zero, package-owned RTC operation order가
> 동일한 process-local solve/export lineage로 결속되었다.

다음은 계속 false다.

- broad 또는 process-wide `iteration_host_copy_zero`
- pre-window DMA, setup/source-apply/teardown, case 사이 transfer zero
- raw/fresh binding, direct ctypes/dlsym/C extension, third-party ROCm 관찰
- 전체 프로세스의 관계없는 추가 solve/export 부재
- 모든 case가 같은 runtime 또는 stream을 공유한다는 주장
- ordinal chain 자체가 kernel 의미론적 실행이나 device content를 증명한다는 주장
- actual external `gfx1100`, unsigned `20/20`, general multiarchitecture parity
- detached receipt 단독 provenance, signature, persistent external log
- hostile same-process Python mutation, monkeypatch 또는 dynamic interposition 저항
- ResultIR, reaction/member-force recovery, energy closure
- end-to-end `O(N)`, speedup, promotion eligibility, commercial readiness

## 구현 및 검증 자산

- `src/structural_analysis/engine_v2/assembly_backend/fgmres_model_family_audited_parity_v2.py`
- `src/structural_analysis/schemas/hip_fgmres_model_family_audited_parity_v2.schema.json`
- `tests/test_engine_v2_hip_fgmres_model_family_audited_parity_v2.py`
- `tests/test_engine_v2_hip_fgmres_model_family_parity_v2_hardware.py`

집중 회귀는 canonical happy path 외에 missing/duplicate/foreign context, wrong expected
context, cross-run global splice, common kernel-lineage splice, retained result mutation,
detached claim/order/triple-hash/counter/logical-key/schedule/zero-launch/safe-integer/type
forgery, package ABI/source/canonical/checkpoint/program-descriptor 위조, 모든 object-level
unknown property, factory exact direct-call AST 및 export/seal 호출 금지를 포함한다.

## 현재 검증

- identity-token-hardened current-source focused synthetic/attack/lifecycle:
  `16 passed in 137.54s (0:02:17)`
- current-source public API/capability: `16 passed`
- previous adjacent family/transfer/public/capability: `40 passed in 61.05s`
- previous adjacent launch/fence ordinal audit: `11 passed in 242.00s (0:04:02)`
- previous RTC v2 full: `134 passed in 43.69s`
- actual v0.2.41 `HipFgmresRtcOperationCounterV1`의
  `attempt/success/rejected/ambiguous/in_flight` 형태를 직접 사용한다.
- identity-token 패치 전 source의 required local `gfx1030` 10-slot gate:
  `1 passed in 3171.31s (0:52:51)`, CPU fallback 없음
  - local family `10/10`(matrix `10/20`)
  - recurrence bound-runtime copy attempt `0`
  - completion D2H `30/30/0`, `4,408` bytes
  - owned memset `80/80/0/0/0`, launch `1,230/1,230/0/0/0`,
    terminal-chain fence `30/30/0/0/0`
- 이 actual 결과는 패치 전 source의 작업 세션 관찰이며 별도 persistent log, signature
  또는 standalone hardware provenance receipt가 아니다.
- token-hardened current-source actual local `gfx1030` 통합 gate:
  `1 passed in 7820.35s (2:10:20)`, CPU fallback 없음
  - v0.2.42 exact 10-slot audited totals와 동일한 `10/10`, D2H `30/30/0`,
    `4,408` bytes, memset `80/80/0/0/0`, launch `1,230/1,230/0/0/0`,
    fence `30/30/0/0/0`
  - 같은 실행에서 v0.2.43 converged 7개 ResultIRV2 bridge와 v0.2.44 7-ready/
    3-not-issued disposition을 만들고 context close 뒤 다시 검증
  - unsigned 비영속 작업 세션 관찰이며 standalone/signed provenance 또는 promotion
    증거가 아님

## 다음 단계

1. 외부 reviewer/HSM 및 actual `gfx1100`은 외부 의존 상태로 유지한다.
2. v0.2.43 [HIP FGMRES ResultIR v2](engine-v2-hip-fgmres-result-ir-v2.md)의 contract와
   v0.2.44 7-ready/3-nonconverged disposition은 완료됐다. `1 passed in 169.10s` 단일-case
   actual 기록은 identity-token 패치 전 source의 역사 관찰이다. Token-hardened
   current-source single-case 범위를 포함한 10-slot aggregate hardware gate도 통과했다.
3. 그 뒤 AI 경로는 dense v1 projection을 승격하지 않고 sparse `ExecutionPlanV2` JVP
   기반 projected-residual shadow를 추가한 뒤 fixed E(3) feature bank를 연결한다.
