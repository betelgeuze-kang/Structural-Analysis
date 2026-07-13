# Engine v2 HIP allocation lineage foundation v1

- 상태: Phase 0 foundation 구현 및 FreeSpace/Krylov/FGMRES resource-owner 통합 완료, `foundation_non_promoting`
- 범위: process-local HIP allocation 소유권·세대·범위·borrow/free 상태기계
- 상위 기준: [Structural Solver Engine v2 마스터 로드맵](structural-solver-engine-v2-master-roadmap.md)
- 다음 소비자: canonical FGMRES device predecessor producer와 mask-domain validator

이 단계의 목적은 장치 포인터 주소만 전달하던 기존 경계를 소유자가 발급한 allocation capability로 바꾸는 것이다. Capability는 “이 주소가 지금 이 owner가 관리하는 정확한 allocation 세대다”라는 process-local 수명 증거이며, 직렬화하거나 다른 process에서 재생할 수 없다.

이 foundation 자체는 solver, allocator 영수증, 수치 정합성 또는 상용 준비를 증명하지 않는다. FreeSpace/Krylov 통합은 v0.2.18, FGMRES parent3+owned8 resource-owner 통합은 v0.2.19에서 별도 검증되었다. 그 후에도 device content와 mask를 생산·검증하지 않았으므로 `authoritative_predecessor_proven`은 false다.

## 1. 해결하려는 실패 모드

기존 raw pointer snapshot만으로는 다음을 구분할 수 없다.

- 같은 주소가 해제 뒤 다른 allocation에 재사용된 ABA
- 다른 owner 또는 다른 GPU가 가진 같은 정수 주소
- allocation 중간을 base처럼 제출한 shifted alias
- 실제 allocation extent보다 긴 역할 descriptor
- parent close/free와 child kernel 사용의 경쟁
- 여러 buffer 중 일부만 borrow한 뒤 실패하는 부분 획득
- `hipFree` 성공 여부가 확정되지 않았는데 live로 되돌리는 위험한 재시도

Lineage foundation은 주소, exact byte extent, element type, owner identity, runtime domain, device ordinal과 monotonic generation을 하나의 capability에 결속한다. 공개 객체를 변조하거나 모방해도 registry의 private snapshot과 일치하지 않으면 다음 사용에서 거부한다.

## 2. Capability 계약

각 live allocation은 최소한 다음 값을 가진다.

| 필드 | 의미 |
| --- | --- |
| `allocation_id` | process-local 단일 allocation 식별자 |
| `role` | owner 내부의 의미적 buffer 역할 |
| `base` | allocator가 반환한 exact base 객체 |
| `pointer_snapshot` | `uintptr_t`로 검증한 exact nonzero base |
| `nbytes` | 양의 exact allocation extent |
| `element_type` | `f64`, `i32`, `u8` 중 하나 |
| `generation` | 같은 domain/device에서 발급될 때마다 증가하는 process-local 세대 |
| `owner_identity` | capability를 발급한 process-local owner |
| `runtime_domain` | native process domain 또는 private injected-test domain |
| `device_ordinal` | 실제 owner가 선택한 nonnegative HIP device |

`f64`와 `i32`는 각각 8-byte와 4-byte 정렬을 요구하며 `nbytes`도 element size의 배수여야 한다. `base+nbytes`가 `uintptr_t`를 넘거나 같은 runtime-domain/device의 live range와 한 byte라도 겹치면 발급하지 않는다. Python `bool`은 `int`의 하위형이지만 pointer, extent, generation 또는 device 값으로 인정하지 않는다.

Capability와 lease는 일반 constructor로 만들 수 없는 immutable process-local 객체다. 정상 API가 arbitrary pointer를 global registry에 등록하는 진입점은 제공하지 않는다. Allocation을 실제로 수행한 owner의 private 발급 경로만 registry를 변경할 수 있다.

## 3. Runtime domain과 generation

현재 Engine v2는 explicit HIP context handle을 소유하지 않는다. 따라서 loader-issued native runtime은 Python wrapper나 `dlopen` handle이 달라도 같은 process/device의 primary-context VA를 공유할 수 있다고 보수적으로 가정해 하나의 native process domain으로 합친다. Device ordinal은 domain key에 별도로 포함한다.

Device ordinal은 preallocated poison witness 범위인 `0..255`로 제한한다. 한 device의 malloc 결과가 불확실해도 해당 ordinal만 fail-closed poison하며, 같은 runtime domain의 다른 device allocation을 강제로 quarantine하지 않는다. 이 고정 크기 witness는 poison marker를 기록하는 순간 추가 container allocation에 실패하더라도 device별 차단 상태를 잃지 않기 위한 것이다.

Injected test runtime은 객체 identity로 분리하고 weak identity witness로 추적한다. Live owner/capability가 runtime을 직접 보존하므로 Python `id()`가 재사용되어도 다른 runtime이 같은 domain을 상속하지 않는다. 마지막 live artifact와 runtime이 사라지면 test-domain generation, poison, quarantine tombstone도 함께 정리한다. 이 private test domain의 증거를 native HIP provenance로 승격하지 않는다.

Registry는 `(runtime domain, device)`별 bounded generation high-water를 live range 제거 뒤에도 유지한다. 따라서 같은 주소가 재사용되면 반드시 이전 capability보다 큰 generation을 받으며, pointer별 unbounded high-water map을 만들지 않는다. 발급 transaction이 commit되지 못하면 active row, owner generation, process-local allocation ID와 high-water 갱신을 하나의 직렬화된 구간에서 rollback하고 외부 allocator가 회수해야 할 성공 pointer를 숨기지 않는다.

Allocator가 겹치는 range를 반환하면 새 결과만 해제해 기존 allocation까지 무효화할 수 있으므로 외부 free 성공을 인정하지 않는다. 새 orphan과 겹친 기존 allocation을 모두 poison하고 range tombstone을 남긴 뒤, 각 owner가 별도 quarantine으로 수명을 종료한다. 끝 주소를 검증할 수 없는 overflow 결과는 `[base, UINTPTR_MAX]` 전체를 보수적으로 막는다.

## 4. 원자적 exclusive borrow

FGMRES는 free-space와 Krylov 등 서로 다른 owner의 여러 buffer를 한 번에 빌려야 한다. Group borrow는 하나의 registry lock 구간에서 다음을 모두 검증한 뒤 all-or-none으로 commit한다.

1. 입력 tuple의 형태, 중복과 기대 역할
2. 모든 capability의 constructor provenance와 immutable snapshot
3. exact active allocation row, generation과 owner
4. 동일 runtime domain과 device 요구
5. 기존 borrow/free-pending 상태 부재

한 항목이라도 실패하면 어느 allocation에도 borrow 표식을 남기지 않는다. 성공 lease는 정확한 capability 집합, borrower identity와 발급 nonce를 결속한다. Lease가 살아 있는 동안 해당 allocation의 free와 owner cleanup을 금지한다.

Release는 exact lease에 대해 원자적이고 재시도 가능해야 한다. 이미 정상 release된 같은 lease의 반복 호출은 idempotent하게 취급할 수 있지만, 복제·foreign·변조 lease나 registry 일부가 바뀐 상태를 성공으로 숨기지 않는다.

Borrow 도중 `ctypes.c_void_p`의 내부 값이나 capability snapshot이 변하면 release authority 자체를 잃지 않는다. Exact borrow lease가 reservation을 종료하고 해당 allocation을 `POISONED`로 수렴시킨 뒤 owner가 private pointer/extent snapshot으로 quarantine한다. 손상된 공개 capability를 다시 device free 대상으로 사용하지 않는다.

## 5. Free handshake와 불확실성

Lineage registry에서 `free`는 “의도”와 “성공 확인”을 분리한다.

```text
LIVE --begin_free(exact owner)--> FREE_PENDING
FREE_PENDING --external hipFree success + exact acknowledgement--> FREED
FREE_PENDING --outcome uncertain--> QUARANTINED (not reusable)
```

`begin_free`는 active borrow가 없고 exact owner/capability가 모두 유효할 때만 single-use free lease를 발급한다. Registry module이 성공하지 않은 `hipFree`를 성공으로 간주하거나 임의 caller의 boolean 주장만으로 active row를 제거해서는 안 된다.

특히 native call이 수행된 뒤 예외가 발생해 실제 free 여부를 알 수 없다면 allocation을 다시 `LIVE`로 돌리지 않는다. `QUARANTINED` 상태는 같은 base의 재등록과 재-free를 막고 cleanup failure를 가시적으로 유지한다. 이 v1 foundation은 “free가 일어나지 않았다”는 별도 retryable transition을 공개하지 않으며 success 또는 uncertainty quarantine만 받는다.

Free lease는 capability의 mutable `base` 객체와 별도로 immutable `pointer_snapshot`, runtime domain과 device를 보관한다. 이 foundation을 기존 context에 연결할 때는 반드시 `runtime.free(ctypes.c_void_p(lease.pointer_snapshot))`가 성공한 직후 exact acknowledgement를 호출한다. Free 실패 시 기존 context의 cleanup-owner 규약과 lineage 상태를 함께 보존해야 하며, 두 상태 중 하나만 성공한 것처럼 보이면 안 된다.

성공한 malloc 뒤 capability publication이 실패하면 pre-reserved orphan cleanup lease를 예외에 실어 반환한다. Pointer가 정확하면 외부 free 성공 후 orphan acknowledgement가 가능하고, pointer가 없거나 결과가 겹치거나 free 결과가 불확실하면 quarantine만 허용한다. Malloc 자체가 `KeyboardInterrupt`/`SystemExit` 등으로 끝나 결과 유무를 알 수 없으면 runtime domain을 fail-closed poison하고 후속 allocation을 차단한다.

## 6. 연속 검증과 concurrency

모든 borrow, release, begin-free, acknowledgement와 owner cleanup은 발급 시 private snapshot을 다시 확인한다. 최소 검증 대상은 다음과 같다.

- capability/lease object identity, issuer와 nonce
- 공개 field의 exact type과 값
- base object identity와 현재 pointer value
- owner/runtime/domain/device identity
- allocation id, role, extent, element type과 generation
- registry row의 active state와 exclusive holder

Registry lock 안에서 user callback, allocator, `hipFree` 또는 device API를 호출하지 않는다. 따라서 외부 runtime의 reentrant callback이 registry 중간 상태를 관찰하거나 같은 lock을 역순으로 획득하지 않는다. 향후 context 통합의 lock 순서는 solver/parent lifetime lock 뒤 lineage transaction, 그리고 device 호출 순으로 고정하되 parent lock을 장시간 HIP 작업 전체에 걸쳐 잡지 않는다.

Capability publication은 별도 process-wide publication lock의 context-managed 구간에서 commit/rollback한다. Borrow/free reservation은 runtime device 재검증 전 임시 상태를 만들고, callback 뒤 lease와 모든 capability private row를 다시 검사한 후에만 commit한다. Release, free/orphan acknowledgement와 owner close는 weak terminal marker를 먼저 기록하고, 비동기 예외 뒤 retry가 남은 active row를 완결할 수 있게 한다. 정상 종료 artifact는 weak tombstone으로만 남기고 quarantine range는 겹치거나 인접한 구간을 합쳐 registry 증가를 제한한다.

Owner, capability, borrow lease와 free lease는 caller handoff 직전 단발성 비동기 예외도 고려한다. Commit marker 이전이면 reservation을 rollback하고, allocation terminal marker 이후면 owner thread witness와 orphan row를 완결한 같은 capability를 반환한다. Domain poison sweep이 중간에 끊겨도 모든 capability 검증·borrow·begin-free·quarantine 경로가 per-device witness를 다시 보고 아직 `live`인 private row를 지연 poison한다.

v0.2.19의 owner-control 확장은 fresh owner를 registry lock 안에서 exact token, canonical owner role, 순서 보존 role allowlist에 예약한다. 예약된 owner의 allocate/free/orphan/poison/close mutation과 controlled capability의 borrow admission은 같은 exact token 없이는 상태를 바꾸지 않는다. Owner별 successful allocation publication count는 free 뒤에도 감소하지 않으며 publication rollback에는 복원되고, caller handoff가 성립한 allocation에는 정확히 한 번만 반영된다. 따라서 FGMRES는 현재 snapshot이 owned8이라는 사실뿐 아니라 fresh reservation 이후 성공 publication이 정확히 8회였음도 prepare와 commit에서 재검증한다. 비예약 owner의 기존 mutation 및 arbitrary borrower 동작은 유지한다.

## 7. 이번 단계의 claim boundary

Foundation 구현과 단위 검증만으로 true가 되는 것은 다음에 한정한다.

- process-local owner-minted allocation identity
- exact range/type/alignment/overflow 검사
- runtime-domain/device별 overlap와 generation high-water
- multi-owner all-or-none exclusive borrow
- borrow 중 free 금지와 explicit free lifecycle
- post-malloc orphan cleanup authority와 overlap poison/quarantine
- mutable pointer drift·device drift·비동기 예외의 fail-closed cleanup
- stale/foreign/tampered capability·lease fail-closed

다음은 foundation v1 단독 증거에서는 계속 false다. FreeSpace/Krylov와 FGMRES resource-only 수명 통합은 각각 후속 계약에서 구현됐지만 수치 predecessor 승격과는 분리한다.

- free-space/Krylov의 실제 모든 `malloc/free` 경로가 lineage로 관리됨(후속 통합 계약에서 완료)
- FGMRES parent3+owned8 resource lease와 allocator provenance(후속 [live checkpoint context v1](engine-v2-hip-fgmres-live-checkpoint-context-v1.md)에서 완료); device content를 가진 생산 predecessor 발행은 미완료
- device memory content 또는 exact predecessor mask를 host가 관찰함
- authoritative allocator/fence/solver receipt
- invalid-source destination all-or-nothing
- later Arnoldi columns/restarts와 final guard
- full CPU/HIP parity, iteration host-copy zero, O(N), speedup
- PCG/AMG/DD, Newton, FE 제품 범위, AI 최적화와 상용 준비

## 8. 통합 순서

1. **v0.2.18 완료**: free-space의 12개 owned allocation에 owner-minted lineage를 붙이고 immutable free target 및 successful free acknowledgement를 close/failed-open cleanup에 연결한다.
2. **v0.2.18 완료**: Krylov의 9개 owned allocation에도 같은 계약을 적용하고, parent에서 빌린 5개 buffer를 lineage capability로 교체한다.
3. **v0.2.19 완료**: FGMRES live context가 필요한 parent 3개와 solver-owned 8개 buffer를 하나의 atomic group lease로 획득하고 fresh/exclusive peer owner와 semantic-last cleanup에 결속한다.
4. 실제 source-apply/Jacobi completion fence와 production prefix를 결속한 predecessor를 발행한다.
5. D2H 없이 device-side mask-domain validator를 실행하고 receipt에는 `actual_mask_host_observed=false`를 명시한다.
6. 그 뒤에만 caller-attested checkpoint context를 live-parent transaction으로 대체하고 invalid-source 원자성, later columns/restarts와 full parity로 진행한다.

## 9. v0.2.17 검증 근거

- focused lineage 계약·적대적 lifecycle·50-cycle registry 회귀: `160 passed`
- 독립 재현 감사의 terminal marker, caller handoff, publication rollback, mutable pointer drift와 per-device poison 집중 검증: `16 passed`
- checkpoint/HIP-context/lineage 인접 회귀: `418 passed`; free-space/Krylov 인접 회귀: `62 passed`
- 광범위 Engine v2 `1332 passed`와 ModelIR/MGT v2·parser `96 passed`, 합계 `1428 passed`; 그 안의 전체 FGMRES 수집 항목 `538 passed`; skip/fallback 없음
- capability matrix `7 passed`; 기존 core/MGT parser 호환 조합 `33 passed`
- Ruff, format check와 `py_compile`: 통과
- source SHA-256: `2ffe5e27aec23ba5edfd244f89e9a7a63e21030fd0b28b05b1bfbd2c65a6788a`
- test SHA-256: `7551d6dc8200cdd2e9c9007f79e7aa9823b8995d054aadbe3f3af1c41fd6cc81`
- wheel: `715263` bytes, SHA-256 `c53ebca3fb8717fa724e9758310f9c022d6333d44585153f5e80ae4abc459632`; isolated target에서 public API와 packaged HIP kernel resource import 확인

이 v0.2.17 focused suite와 해시는 foundation 자체의 회귀 근거이며 promotion receipt가 아니다. 실제 FreeSpace/Krylov 연결과 RX 6900 XT hardware gate 결과는 후속 [v0.2.18 통합 계약](engine-v2-hip-free-space-krylov-allocation-lineage-v1.md)에 별도 기록한다.

## 10. v0.2.19 owner-control 확장 근거

- allocation-lineage/control 전체: `220 passed`
- FGMRES solver-child lease: `45 passed`; live checkpoint context: `42 passed`
- reserve-vs-allocate와 reserve-vs-close 원자 경쟁 각각 `50/50`, 동시 split/final/recover 각각 `20/20`, hang/deadlock 0
- controlled-only/mixed group foreign borrow의 all-or-none 무변경 거부와 exact controller-token borrow 성공
- publication rollback count 복원, return/STORE 중단 뒤 정확히 1회 count, extra publication→free→현재 exact8 재구성 거부
- 독립 재감사: `BLOCKER/HIGH/MEDIUM/LOW = 0/0/0/0`

이 확장은 process-local resource authority를 강화한다. Device content, mask, fence-produced predecessor, solver 수치 또는 signed promotion 증거는 추가하지 않는다.
