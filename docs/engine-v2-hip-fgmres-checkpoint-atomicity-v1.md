# Engine v2 HIP FGMRES checkpoint invalid-source atomicity v1

- 상태: v0.2.21 implemented, `contract_only`
- 증거 범위: exact registered nonoverlap allocation, same stream, exclusive source ownership, fixed four-row raw checkpoint transaction
- 수치 커널: [initial + first-column checkpoint recurrence v2](engine-v2-hip-fgmres-initial-recurrence-v2.md)
- Host owner: [first-column checkpoint transaction context v2](engine-v2-hip-fgmres-checkpoint-context-v2.md)
- 전체 설계: [HIP FGMRES full recurrence ABI v2](engine-v2-hip-fgmres-recurrence-abi-v2.md)

v0.2.21은 multi-block `COMMIT_CHECKPOINT`가 각 lane의 source를 검사하면서 바로 destination을 쓰던 경계를 닫는다. 늦은 lane에서 NaN/Inf를 발견했을 때 앞선 block이 이미 `solution_x` 또는 `true_residual`을 변경할 수 있었으므로, source 검사와 destination copy를 서로 다른 kernel row로 분리했다. 이 문서의 atomicity claim은 아래에 적은 등록·stream·ownership 전제가 모두 성립하는 raw fixed-four-row transaction에만 적용한다.

## 1. Fixed four-row transaction

`E0=26+14S`, `Q=14S`의 valid predecessor에서 host는 outcome을 읽어 분기하지 않고 다음 네 row를 같은 stream에 순서대로 제출한다.

| 순서 | schedule epoch | 계약 |
| --- | --- | --- |
| `CHECKPOINT_DECIDE` | `E0 -> E0+1` | pending outcome을 만들고 sealed 경로는 `armed(1) -> consumed(2)`로 전이한다. |
| `PREFLIGHT_COMMIT_SOURCE(mode=9)` | `E0+1`, non-advancing | `commit_required=true`일 때 `work_w[k]`와 `V[M,k]`만 검사한다. Source 또는 destination을 쓰지 않는다. |
| `COMMIT_CHECKPOINT` | `E0+1 -> E0+2` | 모든 lane이 preflight ticket, active/error state와 exact snapshot shape를 확인한 뒤 pure copy만 수행한다. Late finite check는 없다. |
| `CHECKPOINT_FINALIZE` | `E0+2 -> E0+3` | pending outcome을 검증·발행하고 snapshot을 먼저 지운 뒤 validation state를 마지막에 `0`으로 clear한다. |

성공 종료는 기존과 같은 `E=29+14S`, `Q=14S`다. Preflight가 non-advancing이므로 새 row가 생겨도 numerical schedule epoch의 최종값은 바뀌지 않는다. Checkpoint transaction schedule은 `sha256:2423da989b6cd419b7c4bef46d6c76f2120825a0c840cb516803bb2643ca11e5`다.

## 2. Preflight와 state contract

새 vector mode는 `PREFLIGHT_COMMIT_SOURCE=9`, 새 `predecessor_validation_state`는 `commit_preflighted=3`이다. State 3은 성공 verdict가 아니라 fixed transaction의 preflight ticket이다.

- caller-attested legacy: `empty(0) -> commit_preflighted(3) -> empty(0)`
- device-sealed path: `armed(1) -> consumed(2) -> commit_preflighted(3) -> empty(0)`
- sealed `2 -> 3` 전이는 mask와 reduction-epoch snapshot을 그대로 보존한다.
- preflight는 snapshot을 변경하지 않는다.
- finalizer는 snapshot·mask·나머지 transient를 먼저 clear하고 state `3 -> 0`을 마지막에 수행한다.

Preflight의 block 0은 허용된 `0` 또는 `2`에서 `3`으로 atomic ticket을 발행한다. 같은 launch의 다른 block은 `0`, `2`, `3`의 일시적 관찰을 허용하되 read-only source scan만 수행한다. 이미 state 3인 별도 duplicate preflight의 block 0은 terminal fail-closed한다.

`commit_required=false`에서는 preflight와 commit 모두 source와 destination을 읽거나 쓰지 않지만 state 3 ticket은 발행해 fixed lifecycle을 유지한다. `commit_required=true`에서 비유한 source를 찾으면 error bit 4, failure origin vector 2, termination code 47(`RestartStateFailed`), `active=0`으로 종료하며 두 destination 전체를 보존한다. 이어 제출된 commit은 `active=0` admission에서 copy를 수행하지 않는다.

Multi-block failure diagnostics는 first-error atomic CAS latch가 한 번만 발행한다. 따라서 늦은 block의 generic invalid-control 경로가 먼저 고정된 nonfinite-input error 4/code 47을 error 1/code 40으로 덮어쓰지 못한다.

Commit admission은 모든 lane에서 다음을 요구한다.

- state 3
- `active=1`
- `device_error_bits=0`
- legacy exact zero snapshot 또는 sealed exact mask/reduction snapshot
- 같은 stream에서 먼저 완료된 preflight row

HIP stream의 kernel boundary가 grid-completion ordering을 제공하므로 COMMIT에는 source finite 검사나 destination rollback이 없다.

## 3. Memory와 telemetry

유효한 commit 경로의 추가 비용은 두 source를 한 번 읽는 parallel O(F) preflight다. 새 O(F) workspace, allocation, H2D, D2H, intermediate sync와 fallback은 product path에 추가되지 않았다. Existing `work_w`, `V[M]`, `solution_x`, `true_residual`과 256-byte control만 사용한다.

이 사실은 fixed row의 local complexity와 telemetry 계약이다. Full recurrence, end-to-end solver O(N), latency 또는 CPU 대비 speedup을 증명하지 않는다.

## 4. 검증과 identity

v0.2.21 focused 검증은 다음을 포함한다.

- recurrence plan/schema `63 passed`
- HIPRTC owner/source contract `100 passed`
- actual RX 6900 XT `gfx1030` native recurrence `13 passed`
- native repeated race stress `5/5`
- checkpoint context 신규·인접 focused `77 passed`
- full checkpoint context `261 passed in 523.33s (0:08:43)`
- 전체 Engine v2 회귀 `1670 passed in 1496.65s (0:24:56)`
- capability matrix `7 passed`, Draft 2020-12 schemas `42/42 valid`
- source preflight destination access count 0
- late-lane invalid source에서 `solution_x`와 `true_residual` 전체 raw byte sentinel 불변
- valid legacy/sealed `0 -> 3 -> 0` 및 `2 -> 3 -> 0`, gate-false source/destination no-read

독립 감사 중 late-block diagnostic overwrite race, predecessor state-code source-ABI binding 누락, same-kind row mutation과 preflight/commit pointer TOCTOU, `control_state`/`solve_record` 8-byte alignment 누락을 발견해 수정했다. 현재 context는 complete row fields와 canonical tuple identity, kernel/token/stream/policy/exact 11-pointer tuple을 frozen binding으로 고정하고 각 dispatch 전에 drift를 거부한다. 최종 감사에서 남은 High/Medium 결함은 없었다.

Full context 전수 회귀는 Ruff format/check, Python bytecode compile, canonical schedule/combined identity와 actual HIP source hash assertion도 함께 통과했다.

현재 identity는 다음과 같다.

- predecessor validator schedule: `sha256:b083896de86a808b1398d0fde4abe73726cb91f50399651274ef82dc09a5ef58`
- checkpoint transaction schedule: `sha256:2423da989b6cd419b7c4bef46d6c76f2120825a0c840cb516803bb2643ca11e5`
- combined recurrence ABI: `sha256:bb5b94457fbf3be4c5f2b38dda3f50c8a757094e0b97fb4d7288e7bdbf4db39f`
- fixed HIP source: `sha256:ce4353f61fc3e8cd1311ad52ce50f21a677c7bfa865a2656aa5447b6ec104a83`

v0.2.20 canonical producer의 validator/combined/source와 기존 three-row checkpoint schedule은 historical identity다. Canonical producer receipt나 v0.2.16 caller-attested context의 과거 검증 결과를 이 v0.2.21 raw atomicity 증거로 소급 승격하지 않는다.

## 5. Claim boundary

현재 true인 claim은 다음 하나로 한정한다.

> exact registered nonoverlap allocation, same stream, exclusive source ownership과 fixed `DECIDE -> PREFLIGHT -> COMMIT -> FINALIZE` sequence에서 invalid commit source가 발견되면 `solution_x`와 `true_residual`은 transaction 시작 전 bytes를 모두 보존한다.

다음은 이 단계에서 증명하지 않았다.

- arbitrary raw duplicate COMMIT에 대한 device-only 차단
- transaction 중 외부 kernel, DMA 또는 다른 stream이 source/destination을 쓰는 경우
- 겹친 allocation, shifted raw pointer 또는 미등록 pointer의 atomicity
- device fault나 process failure에 대한 durable transaction
- canonical conditional capability의 live transaction 소비
- sealed lifecycle과 invalid-source 공통 분기는 각각 native 검증됐지만 sealed+invalid-source 조합 전용 native case
- authoritative predecessor 또는 authoritative checkpoint transaction
- actual mask/verdict의 host 관찰
- later columns/restarts, full recurrence, solver/solution receipt
- iteration host-copy zero, full CPU/HIP parity, O(N), speedup, signed promotion, commercial readiness

다음 순서는 canonical producer가 발행한 still-open conditional capability 아래에서 sealed predecessor를 소비하는 live transaction owner를 만들고, 그 뒤 later column/restart와 final guard로 확장하는 것이다.
