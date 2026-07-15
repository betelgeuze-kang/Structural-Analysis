# Engine v2 HIP FGMRES signed release-identity binding v2

## 상태

- 로드맵 작업 마일스톤: `v0.2.36`
- 구현 기준 pushed audit baseline: `59a09585884585cff29b0c6a35667b4502334646`
- 작업 상태: `codex/engine-v2-v0.2.27-completion-export-20260714` feature-branch publication milestone; `origin/main` 병합을 주장하지 않음
- 목표 범위: full release-identity receipt hash의 serialized Ed25519 binding
- package 활성 신뢰 키: `0`
- 실제 외부 `gfx1100` signed cell: `0/10`
- promotion 및 commercial readiness: `false`

이 계약은 v0.2.34가 fresh replay로 만든 전체 release-identity receipt hash를
runner의 서명 대상에 직접 포함한다. v0.2.35 ledger가 v1 signed receipt와 identity
receipt를 acceptance 뒤에 join하던 경계와 달리, v2에서는 runner가 제출한 canonical
payload 자체가 exact identity receipt schema/hash를 서명한다.

이는 실제 runner key 등록, 실제 GPU 실행, hardware-root attestation 또는 외부
monotonic anchor를 대신하지 않는다. 공개 package trust registry가 비어 있으므로
제품 공개 경로는 계속 fail-closed하며, 성공 경로는 임시 합성 키 기반 contract
회귀에서만 실행한다.

## v1과 분리된 wire 계약

v2는 v1 envelope를 감싸거나 v1 signature를 사후 join하지 않는다. 다음 항목을
모두 별도 version과 domain으로 고정한다.

- challenge schema v2
- signed payload schema v2
- signed evidence envelope schema v2
- signed evidence receipt schema v2
- v2 전용 domain-separated Ed25519 message prefix
- durable adapter를 위한 v2 전용 ledger namespace와 receipt schema

v2 verifier는 v1 schema/domain/envelope를 받지 않고, v1 verifier도 v2의 추가
identity field와 schema const를 거부한다. 따라서 동일 release-binding hash를 가진
서로 다른 identity receipt나 version downgrade로 identity binding을 우회할 수 없다.

## Challenge 발행

호출자는 release-binding이나 identity hash를 직접 제공하지 않는다. 발행 API는
v0.2.34가 mint한 process-local verified-release capability만 받고 다음 순서를
수행한다.

1. retained wheel/source/dependency/recipe artifact를 fresh replay한다.
2. verified release의 release binding과 identity receipt를 다시 검증한다.
3. package-owned trust registry에서 exact runner/key epoch와 sequence 범위를 판정한다.
4. challenge에 기존 release-binding hash와 함께 다음 두 field를 넣는다.
   - `expected_release_identity_receipt_schema_version`
   - `expected_release_identity_receipt_hash`
5. 위 field를 포함한 전체 challenge payload로 challenge ID를 계산한다.

Caller-supplied hash, envelope-supplied public key 또는 공개 constructor로 challenge
authority를 만들 수 없다.

## Signed payload와 검증 순서

Canonical v2 signed payload에는 release binding 바로 옆에 다음 field가 필수다.

- `release_identity_receipt_schema_version`
- `release_identity_receipt_hash`

검증기는 challenge를 consume하거나 durable acceptance를 commit하기 전에 다음을
모두 exact equality로 확인한다.

1. v2 challenge의 expected identity schema/hash
2. v2 signed payload의 identity schema/hash
3. fresh replay한 verified-release identity receipt의 schema/hash
4. identity receipt의 `release_binding_hash`
5. signed payload에 포함된 full release binding과 그 `binding_hash`
6. 최종 v2 signed receipt의 identity schema/hash
7. durable path에서는 ledger에 저장한 full identity receipt와 그 hash

이후에만 package trust anchor, Ed25519 signature, fixture registry, external
`gfx1100` lane, exact 10-slot raw solution/residual/solve-record numerical replay를
검증한다. 수치 replay가 끝난 뒤에도 retained release artifact를 한 번 더 fresh
replay하고 최초 snapshot과 exact equality를 확인한 다음에만 pre-commit receipt를
만든다. v1과 v2는 동일 numerical primitive를 공유할 수 있지만 wire parser,
signature domain, challenge mint와 receipt compiler는 공유하지 않는다.

## Durable v2 경계

Durable adapter는 generic owner-private SQLite storage engine만 재사용하고 v1
high-level namespace/receipt는 재사용하지 않는다. v2 namespace의 reservation은 full
challenge, release binding과 full identity receipt를 함께 저장한다.

검증은 v0.2.35와 같은 짧은 two-phase writer transaction을 사용한다.

1. 첫 snapshot transaction에서 exact stored challenge/release/identity를 가져온다.
2. writer lock 밖에서 fresh release replay, v2 signature와 exact 10-slot replay를
   수행한다.
3. commit hook에서 release를 다시 fresh replay한다.
4. 두 번째 transaction에서 snapshot과 identity hash chain을 exact 재확인한다.
5. `accepted_not_before=max(commit_started_at, signed runner completed_at)`를 적용해
   expiry와 storage-clock rollback을 원자적으로 거부한다.
6. durable commit 뒤에만 challenge를 consume하고 v2 durable wrapper를 반환한다.

Commit 뒤 응답 전에 process가 종료된 경우 recovery는 저장 row를 단순 parse하지
않는다. Current release/trust/fixture authority로 v2 signature와 full numerics를 다시
검증하고, 재계산 signed receipt가 저장 receipt와 exact equality일 때만 wrapper를
복원한다.

공개 `audit_hip_fgmres_external_replay_ledger_v2`는 canonical event chain과 local
storage 무결성만 감사한다. 저수준 API로 저장된 envelope의 서명·수치·identity 의미를
승인하지 않으며, semantic authority는 위 recovery의 full 재검증을 통과해야만 mint된다.
두 transaction 사이 reservation/challenge/release/identity snapshot exact equality는
commit path에서 강제되지만, 동시 snapshot 변조를 직접 재현하는 전용 회귀는 후속
증거 보강 항목으로 남긴다.

`acceptance_commit_head_event_*`는 acceptance transaction의 historical commit-time
head다. 이후 event append 뒤의 current ledger head를 증명하지 않으며, current head가
필요하면 별도 fresh audit가 필요하다.

## Receipt와 기존 claim 보존

Public verifier의 성공 결과는 공개 생성할 수 없는 mint-guarded
`HipFgmresExternalVerifiedSignedEvidenceV2` process-local wrapper다. Wrapper는 exact
identity receipt와 signed receipt의 release-binding/schema/hash chain을 생성 시 다시
검증하며, 성공 hook과 실제 challenge consume이 모두 끝난 뒤에만 반환된다.

Detached `HipFgmresExternalSignedEvidenceReceiptV2`와
`validate_hip_fgmres_external_signed_evidence_receipt_v2`는 canonical 구조, 상수,
self-hash를 확인하는 직렬화 projection일 뿐 독립 verification authority가 아니다.
따라서 detached receipt를 직접 구성하거나 validator를 통과한 것만으로 envelope,
signature, numerical replay 또는 challenge consumption을 승인해서는 안 된다.

Pre-commit signed receipt에서 다음 검증 projection이 true다.

- canonical v2 envelope verified
- package trust anchor and Ed25519 signature verified
- fresh-replayed full release-identity receipt schema/hash matched
- signed envelope binds the full release-identity receipt hash
- exact external fixed-suite raw numerical replay completed
- verifier challenge single-use reservation acquired

마지막 항목의 wire field는 `verifier_challenge_single_use_reserved=true`다. Durable
success hook은 아직 consume 전인 이 projection만 저장하며 `consumed=true`라고
주장하지 않는다. Process-local verified wrapper 또는 durable verified wrapper가
성공적으로 반환된 뒤에만 실제 consume 완료를 authority로 취급한다.

v2 signed receipt 자체의 durable claim은 false다. Durable claim은 별도 v2 ledger
receipt/wrapper에서만 true다. 기존 v0.2.33 signed receipt, v0.2.34 identity receipt,
v0.2.35 ledger receipt의 serialized identity-binding false claim은 소급 변경하지
않는다.

## Claim boundary

다음 항목은 v2 contract가 성공해도 계속 false다.

- 실제 운영 runner public key 등록, proof-of-possession과 rotation/revocation 운영
- 실제 external `gfx1100` 실행 또는 local process의 독립 hardware 관찰
- runner honesty, HSM/TPM·secure boot·hardware-root attestation
- external monotonic anchor
- exactly-once delivery와 cross-host/multi-ledger replay 방지
- 동일 UID/root/storage administrator 또는 coordinated package+ledger rollback 저항
- non-POSIX/NFS/FUSE filesystem의 locking·fsync와 controller의 거짓 fsync 저항
- wall-clock authenticity와 물리적 fsync가 challenge expiry/TTL deadline 전에
  완료됐다는 증명
- package/trust/fixture registry rotation을 가로지르는 historical recovery
- later append 뒤의 current ledger head attestation
- remote commit authenticity, reproducible build와 atomic multi-artifact snapshot
- same-artifact `gfx1030`/`gfx1100` two-architecture completion과 promotion
- ResultIR, iteration host-copy-zero, speedup, end-to-end O(N)
- commercial readiness 또는 상용 인증

Package active key는 `0`, actual external `gfx1100`은 `0/10`으로 유지한다. 합성
Ed25519 key와 합성 runner payload는 protocol/numerical verifier 회귀일 뿐 실제
hardware evidence가 아니다.

## 최종 검증

- v2 synthetic exact 10-slot happy path와 identity-binding true claim
- identity hash mutation 후 재서명, same-binding identity substitution 거부
- v1/v2 양방향 downgrade와 signature-domain confusion 거부
- challenge 발행 뒤 artifact drift 거부
- excessive-depth parser bound와 bounded error path
- signed nested family/case receipt의 추가 field 거부
- false claim을 true로 바꿔 재서명한 envelope 거부
- detached receipt 구조 검증과 mint-guarded authority 경계
- public empty-registry path의 무부작용 fail-closed
- durable restart/race, response-loss recovery와 forged low-level row 거부
- storage expiry/rollback 및 later-head append 불변성
- v1 receipt의 false claim과 serialized output 회귀
- JSON Schema Draft 2020-12, public API/resource, Ruff/py_compile
- candidate wheel 포함, 격리 설치/import/reopen audit와 private-key 표식 부재

최종 source의 비중복 회귀는 다음 `240 passed`다.

- signed-evidence v1/v2 전체 `38 passed` (`6 + 7 + 10 + 6 + 9` shard)
- v2 durable replay ledger `11 passed`
- v1 high-level replay ledger `15 passed`
- generic durable ledger와 release/source/wheel/dependency/public/capability 지원 회귀
  `176 passed`

JSON Schema Draft 2020-12 구성, `py_compile`, Ruff lint/format,
`git diff --check`를 별도로 통과했다. 독립 후속 보안 감사 결과는
`BLOCKER 0 / HIGH 0 / MEDIUM 0 / LOW 2`다. 남은 LOW는 envelope schema만으로는
nested v1/v2 receipt의 전체 의미를 판정하지 않고 runtime exact round-trip이 최종
권위라는 점, signed-v2 통합 테스트의 release artifact byte replay가 별도
release-identity 스위트에서 검증되고 해당 통합 경로에서는 stub/call-count로 결합된다는
점이다. Schema-only acceptance나 합성 회귀를 verification authority 또는 hardware
evidence로 승격하지 않는다.

Candidate wheel은 `1137224` bytes, `214` members, uncompressed `6028261` bytes이며
SHA-256은
`00e547a10cc5813be31cbd87f99efec061f1801ce507b6a3787fbbcba1ecfea3`,
`RECORD` SHA-256은
`fa21a45813ddd69bae6557f72d7356c65f2327eab5ed97624d84769e2105eba4`다. 새 v2
모듈 2개와 schema 3개 포함, private-key 표식 부재, 격리 설치 뒤 public import와
v2 ledger initialize/close/reopen/audit를 확인했다.

## 다음 순서

1. trust registry lifecycle와 격리 runner/HSM public-key enrollment
2. 최종 candidate의 실제 external `gfx1100` fixed-suite `10/10`
3. 동일 final artifact의 local `gfx1030` `10/10` 재실행
4. external monotonic anchor와 historical trust/revocation recovery
5. iteration host-copy-zero gate
6. ResultIR integration
7. certificate-bound SPD-gated PCG 상태기계
