# Engine v2 HIP FGMRES live checkpoint context v1

- 상태: Phase 0 resource-lifetime slice와 single canonical producer-child coordination 구현·독립 감사 완료, `contract_only`/non-promoting
- resource 구현 버전: v0.2.19; canonical child 연동: v0.2.20
- 현재 downstream 권위 단계: v0.2.28 explicit terminal-outcome observation 구현; 다음은 full CPU/HIP parity
- 상위 기준: [Structural Solver Engine v2 마스터 로드맵](structural-solver-engine-v2-master-roadmap.md)

## 문서 범위

`HipFgmresLiveCheckpointExecutionContextV1`은 FGMRES 수치 해석기가 아니라, 해석기가 사용할 live checkpoint 자원의 소유권과 수명을 관리하는 resource-only slice이다. Base context의 open/close와 v1 opening receipt는 정확한 Krylov parent, device allocation lineage, FGMRES RTC v2 module, checkpoint token을 하나의 배타적 컨텍스트로 묶지만 kernel launch, 선행 상태 생성, mask 검증, solver iteration, solution 생성은 수행하지 않는다. v0.2.20에는 이 자원을 재할당하지 않고 사용하는 [canonical first-column predecessor producer v1](engine-v2-hip-fgmres-canonical-predecessor-v1.md)을 정확히 한 번 reserve/release하는 child coordination만 추가되었다. Producer 실행 claim은 별도 receipt에 있고 base v1 receipt의 resource-only 의미는 바뀌지 않는다.

현재 계약의 기준은 다음과 같다.

- schema version: `structural-analysis-hip-fgmres-live-checkpoint-context.v1`
- capability profile: `phase0_live_fgmres_checkpoint_resource_owner`
- evidence scope: `allocator_bound_live_checkpoint_resources_non_promoting`
- promotion eligibility: 항상 `false`
- fallback: 없음

권위 구현과 직렬화 계약은 [live checkpoint context source](../src/structural_analysis/engine_v2/assembly_backend/fgmres_live_checkpoint_context_v1.py), receipt 형식은 [JSON Schema](../src/structural_analysis/schemas/hip_fgmres_live_checkpoint_context_v1.schema.json)에 고정된다.

## 자원 구성: parent3 + owned8 = exact11

컨텍스트는 부모에서 이미 생성된 세 capability를 새로 할당하지 않고 대여한다.

1. `reduced_state`
2. `reduced_load`
3. `jacobi_inverse`

그 다음 전용 peer owner가 다음 여덟 capability를 정확한 순서로 소유한다.

1. `solution_x`
2. `true_residual`
3. `work_w`
4. `basis_v`
5. `preconditioned_basis_z`
6. `packed_dense_state`
7. `fgmres_control_state_v2`
8. `solve_record`

최종 live group은 동일한 tuple 객체의 `parent3 + owned8`이며, exact11 capability 전체에 대해 하나의 배타적 borrow lease를 갖는다. 순서, 객체 identity, role, owner identity, generation, runtime domain, device, borrower token 중 하나라도 달라지면 권위 검증은 fail-closed로 종료된다.

## owned device byte 계약

기호는 다음과 같다.

- `F`: free DOF count
- `M`: restart dimension
- `R`: maximum restart count

owned8의 byte 구성은 다음과 같다.

| Buffer | Element/byte extent | Bytes |
| --- | ---: | ---: |
| `solution_x` | `F` doubles | `8F` |
| `true_residual` | `F` doubles | `8F` |
| `work_w` | `F` doubles | `8F` |
| `basis_v` | `(M + 1)F` doubles | `8(M + 1)F` |
| `preconditioned_basis_z` | `MF` doubles | `8MF` |
| `packed_dense_state` | `M² + 5M + 1` doubles | `8(M² + 5M + 1)` |
| `fgmres_control_state_v2` | 256 raw bytes | `256` |
| `solve_record` | `192 + 72R` raw bytes | `192 + 72R` |

따라서 전체 owned device byte와 `memory_budget_bytes` 사전 검증에 사용되는 공식은 다음과 같다.

```text
B_owned = 8[(2M + 4)F + M² + 5M + 1] + 448 + 72R
```

이 값은 parent3의 기존 allocation과 RTC module 메모리를 포함하지 않는다. `context_ready` receipt에서 `managed_device_bytes`, `current_device_bytes`, `peak_device_bytes`, `lineage_capability_mint_bytes`는 이 값과 일치해야 한다.

## peer owner control 계약

owned8은 부모 allocation owner와 별개인 fresh canonical peer owner에서만 생성된다.

- owner role은 `fgmres_checkpoint_owned_buffers`이다.
- owner는 부모의 FreeSpace/Krylov owner와 다른 identity이며, 동일 runtime domain과 device를 사용한다.
- 예약 시점에 generation 0이고, 이전 allocation/free/orphan/allocator activity가 없는 fresh owner여야 한다.
- Krylov parent가 live context의 exact built-in `object` token으로 registry-level exclusive control을 선점한 뒤 semantic reservation을 공개한다.
- control allowlist는 위 owned8 role tuple과 순서까지 정확히 일치해야 한다.
- control 예약 후 `allocate`, `begin_free`, free/orphan/poison resolution, owner `close`를 포함한 모든 mutation은 같은 exact token을 제출해야 한다.
- 다른 token, token 누락, allowlist 밖 role, 외부의 동시 allocate/close는 registry에서 거부된다.

준비 및 commit 경계에서 추가로 다음을 검증한다.

- control 예약 후 successful capability publication이 정확히 8회이다.
- publication은 owned8 canonical order이며 누락, 추가 publication, 순서 바꾸기가 없다.
- cleanup snapshot의 capability tuple이 owned8 객체와 allocation issuance order까지 정확히 같다.
- pending free와 pending orphan이 모두 빈 tuple이다.
- owner의 현재 generation이 마지막 owned capability publication을 나타낸다. generation은 runtime/device domain high-water를 따르므로 숫자 `8`을 의미하지는 않는다.

이 검증은 사전 fresh check와 registry reservation 사이의 TOCTOU, owned8 생성 중의 외부 mutation, 추가 capability를 만들었다가 제거하는 우회를 허용하지 않기 위한 계약이다.

## runtime, device, stream 바인딩

`context_ready`는 단순히 role 목록이 맞는 상태가 아니다. 다음 identity가 직접 바인딩되고 receipt 검증 시 다시 확인된다.

- parent snapshot과 live context의 bound runtime 객체
- loaded HIP runtime owner
- exact stream 객체와 개방 시의 stream pointer snapshot
- selected device ordinal
- exact11 전체의 runtime owner, runtime domain identity, device ordinal
- RTC checkpoint token이 가리키는 loaded runtime과 immutable binding snapshot

전체 자원은 parent와 동일 runtime/device/stream authority 아래에 유지된다. 다만 이 slice는 kernel을 enqueue하지 않으므로 `same_stream_bound=true`는 수명과 권위 바인딩을 의미하지, solver iteration 실행을 의미하지 않는다.

## HIPRTC v2 module과 checkpoint token

기본 native 경로는 FGMRES recurrence v2 kernel을 내부에서 HIPRTC로 compile하고, module cleanup owner를 live context에 handoff한다. live context는 해당 kernel에서 배타적 checkpoint transaction token과 binding snapshot을 획득한다.

- native `hip` receipt은 internally compiled kernel과 non-injected runtime/HIPRTC library provenance를 요구한다.
- caller-supplied kernel은 주로 test-double 경로를 위한 엄격한 handoff로 취급되며 live context가 수명을 인수한다.
- checkpoint token은 다른 owner와 공유되지 않고, close 시 module과 함께 해제된다.
- ready 상태에서 RTC pending stream count는 0이어야 한다.

## v0.2.20 canonical producer child

Ready live context는 process-local child token으로 canonical predecessor producer를 정확히 한 번 reserve할 수 있다. Active child가 있는 동안 base context `close()`는 pre-mutation에서 거부되며, child는 자신의 pending work를 exact-runtime fence/consume으로 종결한 뒤 token을 release해야 한다. 한 child가 terminal release된 live context는 두 번째 canonical producer를 발행하지 않는다. 이 single-use terminal state는 process-local lifetime authority이며 v1 base receipt에 새 수치 claim이나 pointer/handle을 직렬화하지 않는다.

Child는 live exact11을 바꾸지 않고 Krylov parent가 발행한 delegated projection을 검증한다.

- persistent: parent3 + owned8 = 11 capabilities
- delegated operator: reduced CSR row pointer/column indices/values = 3 capabilities
- delegated workspace: reduction ping/pong = 2 capabilities
- physical total: exact16, additional allocation/device bytes = 0

Child는 exact loaded runtime에서 seal한 `hipMemsetAsync`로 owned8을 zero-initialize하고 `INIT`부터 `PREDECESSOR_VALIDATE`까지 exact `27+14S` kernel row를 같은 stream에 제출한다. Validator는 offset 116/120/124에 mask-domain seal을 `empty -> armed`로 남기며 schedule/reduction epoch을 전진시키지 않는다. Product receipt는 D2H 0, H2D 0, intermediate sync 0, fallback 0과 final fence 1을 유지하고 actual mask 또는 validation verdict를 host에 노출하지 않는다.

## open 순서

1. parent, source apply, recurrence/source plan, memory budget을 검증한다.
2. canonical peer allocation owner를 열고 one-slot handoff로 cleanup authority를 공개한다.
3. exact control token을 registry에 예약한 뒤 parent3 semantic child를 reserve한다.
4. parent snapshot에서 runtime, loaded runtime, stream, device, architecture를 고정한다.
5. FGMRES RTC v2 module을 compile/adopt하고 checkpoint token과 binding snapshot을 획득한다.
6. allowlist 순서로 owned8을 할당하고 정확히 8회의 successful publication을 확인한다.
7. exact11 tuple을 parent에 prepare하고, exact token으로 하나의 group borrow lease를 획득한 뒤 commit한다.
8. allocation generation binding hash와 전체 authority를 재검증하고 `context_ready` receipt를 고정한다.

ready 전환은 위 단계가 모두 성공한 경우에만 허용된다. memory budget 초과와 owner 예약 실패는 device allocation 전에 종료된다.

## close와 semantic-last 순서

normal close와 failed-open cleanup은 동일한 역순 소유권 해제 규칙을 따른다.

1. semantic, allocation, checkpoint, group-borrow authority를 복구·재검증한다.
2. RTC kernel/module을 닫고 checkpoint token을 해제한다.
3. exact11 group borrow만 먼저 release한다.
4. owned8을 역순으로 free/retire한다.
5. 잔류 orphan cleanup authority를 성공 확정 또는 quarantine으로 종결한다.
6. peer allocation owner를 exact control token으로 닫는다.
7. parent semantic lease를 마지막에 release한다.
8. 모든 자원이 종결된 후에만 `context_closed`로 전환한다.

semantic lease를 마지막까지 유지하므로 owned8 정리가 끝나기 전에 parent가 새 FGMRES child를 받아들이는 상태를 막는다. parent의 combined release API로 이 순서를 우회할 수 없다.

## failed-open과 interruption-safe handoff

open 중 일반 예외가 발생하면 컨텍스트는 이미 공개된 권위를 복구한 뒤 위 close 순서를 실행한다.

- 정리가 완전히 성공하면 `context=None`, status `unavailable`, stable failure reason을 반환한다.
- 재시도가 필요한 cleanup 실패는 live cleanup owner와 `cleanup_failed` receipt를 보존한다.
- allocator outcome이 확정될 수 없으면 포인터를 다시 free하지 않고 `cleanup_quarantined`로 수렴한다.
- `KeyboardInterrupt` 같은 `BaseException`은 stable `hip_fgmres_live_checkpoint_context_open_interrupted` error로 정규화하며, 정리가 완료되지 않은 경우에만 retryable cleanup owner를 제공한다.

다음 return/STORE 및 부분 publication 경계에 대한 복구 witness가 있다.

- peer owner open handoff
- registry control reservation과 parent semantic token publication
- internal RTC compile/module owner 또는 caller-kernel handoff
- checkpoint-token 획득과 binding snapshot
- owned allocation return 후 capability publication
- exact11 borrow lease 반환과 parent commit
- `begin_free` lease publication, external free 결과, quarantine 수렴
- owner close와 RTC module close의 monotonic terminal witness

복구는 host registry authority를 기준으로 하며 알 수 없는 external allocator 결과를 임의로 성공 처리하지 않는다.

## receipt, backend provenance, 보안 경계

receipt는 context/plan/source hash binding, lease epoch, generation binding hash, kernel provenance, dimensions, owned buffer descriptors, allocation lineage, telemetry, claims, canonical receipt hash를 포함한다. raw pointer, owner identity, lease ID, stream/module/function handle은 직렬화하지 않는다.

`actual_backend`는 임의 label이 아니라 provenance에서 파생된다.

- `hip`: native HIPRTC Krylov parent, parent backend `hip`, internally compiled FGMRES kernel, non-injected runtime/HIPRTC library discovery가 모두 확인된 경우
- `test_double`: injected parent 또는 caller-supplied/injected kernel provenance가 포함된 경우
- `null`: kernel provenance가 확립되기 전의 non-ready failure receipt에서 가능

validator는 schema, canonical hash, backend 파생 규칙, context authority, non-promoting claim을 함께 검증한다. `test_double`을 `hip`으로 또는 그 반대로 재라벨한 receipt는 거부된다.

## claim boundary

`context_ready`에서 참인 claim은 다음 세 가지 resource-lifetime 사실에 한정된다.

- `live_krylov_parent_integrated`
- `allocator_provenance_bound`
- `resource_owner_ready`

다음 claim은 `context_ready`에서도 모두 `false`이며 schema와 semantic validator가 `true`로의 위조를 거부한다.

- `owned_content_initialized`
- `authoritative_predecessor_proven`
- `device_mask_domain_validator_bound`
- `actual_mask_host_observed`
- `checkpoint_transaction_ready`
- `live_solver_ready`
- `solution_ready`
- `iteration_host_copy_zero_proven`
- `asymptotic_o_n_proven`
- `speedup_proven`
- `commercial_ready`
- `promotion_eligible`

즉 buffer descriptor에 예정된 initialization 의미가 있더라도, 현 slice가 그 내용을 생성했다거나 수치적으로 유효함을 입증하지는 않는다. opening telemetry의 H2D, D2H, kernel launch, sync, fallback count는 모두 0이다. close 후에는 ready에 한정된 세 claim도 `false`로 수렴한다.

별도 canonical child의 fenced receipt에서는 `owned_content_initialized`, `canonical_producer_prefix_fenced`, `device_mask_domain_gate_bound`만 추가로 true가 될 수 있다. 이 사실은 base v1 receipt의 위 false 값을 소급해 바꾸지 않는다. Child에서도 `actual_mask_host_observed`, `device_validation_outcome_host_observed`, `authoritative_predecessor_proven`, `checkpoint_transaction_ready`, `invalid_source_destination_atomicity_proven`, solver/solution, host-copy-zero, O(N), speedup, commercial/promotion claim은 계속 false다.

## 확인된 focused verification

아래는 broad suite나 wheel 결과가 아닌, 현 계약과 직접 연관된 focused verification만 기록한 것이다.

- allocation lineage/control: 220 passed
- Krylov FGMRES solver lease: 45 passed
- live checkpoint context: 42 passed
- FreeSpace/Krylov/FGMRES RTC ownership handoff: 169 passed
- common RTC fixed-source compile owner: 23 passed
- actual `gfx1030` native hardware gate: 1 passed
- independent adversarial audit: `BLOCKER/HIGH/MEDIUM/LOW = 0/0/0/0`

native hardware gate는 assembly → resident → FreeSpace → Krylov primitives → live checkpoint 체인에서 `actual_backend="hip"`, internally compiled HIPRTC v2 module, exact11 lease, reverse cleanup, zero fallback을 확인한다. 이 1 pass는 solver iteration, solution 정확도, O(N), 속도 향상, 상용 준비를 입증하지 않는다.

v0.2.20 canonical child의 별도 actual `gfx1030` hardware gate는 같은 live chain 위에서 sealed owned8 memset 8회, exact `27+14S` kernel row, H2D/D2H 0, final fence 1, fallback 0을 확인했다. Verification-only D2H로 mask domain, `reduction_epoch=14S`, `schedule_epoch=26+14S`, state `armed(1)`과 두 snapshot 일치를 확인했지만 product receipt가 mask/verdict를 관찰했다는 증거는 아니다.

## 광범위·배포 검증

- Engine v2 전체: `1608 passed` in `1082.98s`; 실패·오류·skip 0
- ModelIR/MIDAS v2: `83 passed`; 기존 core/MGT parser: `33 passed`
- 실제 RX 6900 XT `gfx1030` FreeSpace/Krylov/live resource hardware chain: `3 passed`; fallback 0
- capability matrix: `7 passed`; Draft 2020-12 schema: `41/41 valid`
- Ruff check, selected v0.2.19 files format check와 `py_compile`: 통과
- selected lineage/Krylov/live/RTC/API source aggregate SHA-256: `bdcc44df6945b318564a743d8c995a33d3db9c553d43478ccb6679546364ea75`
- selected focused test aggregate SHA-256: `31341abdbe1292a051fad5ece61e7b325aa991a3b23369ad4c2ea9b45e0d1e31`
- 41-schema aggregate SHA-256: `77da3e976974d5cc77ea2ae54fbe0f45efd88f7d997fb35c8cacb959260052a2`
- wheel: `780803` bytes, SHA-256 `93e6235fe1b963a3d476e4861d94231ba33d691340b59d09649e87c53cde3d71`

선택 aggregate는 각 `sha256sum` 출력(상대 경로 포함)을 표시된 순서 그대로 다시 SHA-256 한 값이다. 재현 명령은 다음과 같다.

```bash
sha256sum \
  src/structural_analysis/engine_v2/__init__.py \
  src/structural_analysis/engine_v2/assembly_backend/__init__.py \
  src/structural_analysis/engine_v2/assembly_backend/fgmres_live_checkpoint_context_v1.py \
  src/structural_analysis/engine_v2/assembly_backend/fgmres_rtc_v2.py \
  src/structural_analysis/engine_v2/assembly_backend/free_space_rtc.py \
  src/structural_analysis/engine_v2/assembly_backend/hip_allocation_lineage.py \
  src/structural_analysis/engine_v2/assembly_backend/krylov_primitives.py \
  src/structural_analysis/engine_v2/assembly_backend/krylov_primitives_rtc.py \
  src/structural_analysis/engine_v2/rtc_backend/rtc.py | sha256sum

sha256sum \
  tests/test_engine_v2_capability_matrix.py \
  tests/test_engine_v2_hip_allocation_lineage_v1.py \
  tests/test_engine_v2_hip_fgmres_live_checkpoint_context_v1.py \
  tests/test_engine_v2_hip_fgmres_live_checkpoint_hardware_v1.py \
  tests/test_engine_v2_hip_fgmres_rtc_v2.py \
  tests/test_engine_v2_hip_free_space_rtc_v1.py \
  tests/test_engine_v2_hip_krylov_fgmres_solver_lease_v1.py \
  tests/test_engine_v2_hip_krylov_primitives_rtc_v1.py \
  tests/test_engine_v2_rtc_backend_v1.py | sha256sum

rg --files src/structural_analysis/schemas -g '*.schema.json' \
  | sort | xargs sha256sum | sha256sum
```

Wheel을 별도 target에 설치한 뒤 그 target의 `structural_analysis.engine_v2`에서 live context와 owner-control public API를 import하고, packaged live receipt schema와 `engine_v2_fgmres_v2.hip.cpp` resource를 읽어 확인했다. 이 검증은 패키지 완결성 증거이며 수치 solver 승격 증거가 아니다.

## Downstream 권위 진행

이 resource-only receipt 이후 invalid-source destination atomicity(v0.2.21), sealed checkpoint transaction(v0.2.22), later column/restart·final-guard global owner(v0.2.23-v0.2.26), completion-only raw export(v0.2.27)가 각각 별도 contract과 receipt로 구현됐다. 이 downstream 구현은 본 live resource receipt의 수치·solution claim을 소급 승격하지 않는다.

raw `solve_record`와 payload lineage를 해석·검증하는 explicit terminal-outcome observation contract은 v0.2.28의 별도 non-promoting child로 구현됐다. 다음 권위 단계에서 model-family·multi-architecture CPU/HIP full parity와 iteration host-copy-zero를 각각 별도 gate로 닫아야 한다. 그 전에는 현 live checkpoint context나 canonical child, raw export, observer를 authoritative solver/solution, ResultIR-ready 또는 commercial-ready 증거로 승격해서는 안 된다.
