# Engine v2 HIP FGMRES external replay ledger v1

## 상태

- 로드맵 작업 마일스톤: `v0.2.35`
- 구현 기준 pushed audit baseline: `59a09585884585cff29b0c6a35667b4502334646`
- 작업 상태: pushed branch contract-only milestone; `origin/main` 포함은 주장하지 않음
- receipt schema: `structural-analysis-hip-fgmres-external-replay-ledger-receipt.v1`
- capability: `phase0_external_signed_evidence_local_durable_replay_ledger`
- evidence scope: `single_configured_local_posix_sqlite_ledger_cross_process_at_most_once_acceptance_non_promoting`
- package 활성 신뢰 키: `0`
- 실제 외부 `gfx1100` signed cell: `0/10`
- 승격 및 상용화 상태: `false`

이 문서는 v0.2.33의 process-local single-use challenge와 v0.2.34의 독립
release-artifact identity를 하나의 사전 구성된 로컬 durable ledger에 결합한다.
성공한 acceptance를 프로세스 재시작 뒤에도 다시 받아들이지 않는 at-most-once
경계이며, 외부 GPU 실행이나 release promotion 자체를 만들지는 않는다.

## 저장 경계

Ledger API는 directory를 만들지 않는다. 호출자는 current effective UID가 소유하는
절대 경로의 전용 POSIX directory를 미리 만들고 mode를 정확히 `0700`으로 설정해야
한다. 초기화는 그 directory 안에 mode `0600`인 database를 생성하며, 이후 open도
directory `0700`과 database `0600`을 정확히 요구한다. `ledger_id`와 domain 고정
namespace를 모두 지정해 다시 연 capability만 발행·검증 API에 전달한다.

저장 엔진은 표준 라이브러리 SQLite의 고정 database를 사용한다.

- database는 current effective UID 소유의 `0600` regular file이며 single link여야 한다.
- directory와 database FD를 모두 pin하고 symlink, hardlink alias, FIFO, socket,
  device와 path/inode 대체를 거부한다.
- `journal_mode=DELETE`, `synchronous=EXTRA`, `foreign_keys=ON`,
  `trusted_schema=OFF`를 고정한다.
- bounded `BEGIN IMMEDIATE` write transaction이 cross-process writer를 직렬화한다.
- schema manifest, `application_id`, `user_version`, `quick_check`, canonical JSON
  blob과 ordered event hash chain을 fresh open/transaction에서 다시 감사한다.
- challenge, acceptance, campaign과 event row는 append-only이며 update/delete를
  trigger로 거부한다.

SQLite commit이 성공하기 전에는 ledgered challenge 또는 durable acceptance를
반환하지 않는다. 이 경계는 지원 POSIX filesystem과 SQLite의 sync/locking 의미에
의존한다.

## Challenge 발행

발행 순서는 다음과 같다.

1. v0.2.34 verified release의 모든 retained artifact를 fresh replay한다.
2. 현재 package trust registry로 v0.2.33 challenge를 발행한다.
3. full canonical challenge, release binding, release identity receipt를 ledger에
   한 transaction으로 기록한다.
4. `challenge_id`, `request_id`, `(runner_id, run_sequence)` 재사용을 거부한다.
5. 같은 runner의 run sequence는 key epoch나 campaign 변경으로 초기화하지 않고
   기존 최대값보다 커야 한다.
6. campaign은 runner, release/identity, trust/fixture registry identity에 고정한다.
7. durable commit 뒤에만 challenge bytes를 외부 runner에 공개한다.

만료되거나 사용되지 않은 challenge도 sequence tombstone으로 남는다. 자동 삭제,
sequence 재사용 또는 암묵적 ledger rotation은 v1에 없다.

## 재시작 검증과 acceptance

검증 API는 caller가 process-local challenge 객체를 다시 제공하도록 요구하지
않는다. Canonical envelope에서 routing용 challenge identity를 읽고, ledger의
저장 row를 fresh audit한 뒤 저장된 exact challenge payload만 private mint로
복원한다. 이 routing parse 자체는 서명 권위가 아니며, 이어지는 v0.2.33 검증이
envelope schema, Ed25519 signature, release/runtime/device와 10-slot raw numerics를
전부 다시 검증한다.

Routing parse는 ledger transaction 전에 v0.2.33의 `4 MiB`, depth `64`, node
`200,000` 한계와 fail-fast schema 경계를 그대로 적용한다. 초과 nesting은 stable
extent error로 끝나며 challenge/acceptance/event row를 만들지 않는다.

검증은 writer lock을 오래 점유하지 않는 two-phase snapshot 경계다.

1. 첫 번째 짧은 `BEGIN IMMEDIATE` transaction에서 challenge가 ledger-issued이고 아직
   acceptance되지 않았는지 확인하고 reservation, full challenge, release binding,
   release identity의 exact snapshot을 가져온 뒤 writer lock을 해제한다.
2. 저장 challenge의 exact routing 일치, fresh v0.2.34 release-artifact replay,
   저장 release binding/identity의 exact 일치, v0.2.33 Ed25519 signature와 10-slot
   numerical replay를 writer lock 밖에서 수행해 signed receipt를 완성한다.
3. success commit hook에서 current verified release artifact를 다시 fresh replay하고
   commit 시작 시각을 잡는다.
4. 두 번째 짧은 `BEGIN IMMEDIATE` transaction을 열어 reservation, challenge, release
   binding, release identity가 첫 snapshot과 exact 일치하는지 다시 확인한다.
5. envelope/signed-payload/signed-receipt uniqueness와 두 receipt binding을 검증하고,
   acceptance event와 full signed receipt를 durable commit한다.
6. commit 뒤 process-local challenge를 consume하고 combined capability를 공개한다.

Acceptance의 verifier time floor는
`accepted_not_before=max(commit_started_at, signed runner completed_at)`이다. Storage
clock이 기록하는 `accepted_at_utc`는 challenge의 issue/expiry window 안이면서 이
floor 이상이어야 한다. 따라서 precommit 중 expiry가 지나거나 storage clock이
검증 시각보다 뒤로 rollback되면 같은 transaction 안에서 fail-closed하며 acceptance
row와 event를 모두 남기지 않는다.

Commit 뒤 응답 전에 프로세스가 종료되면 일반 재검증은 replay로 거부한다.
저장된 exact acceptance의 recovery는 단순 row parse가 아니다. Current verified
release의 모든 retained artifact를 fresh replay하고 저장 release binding/identity와
exact 일치시킨다. 이어 저장된 `accepted_at_utc`를 historical verification time으로
사용해 current package trust/fixture authority, Ed25519 signature와 exact 10-slot
numerics를 전부 다시 검증하며, 재계산한 signed receipt가 저장 receipt와 exact
equality를 만족할 때만 combined wrapper를 다시 발급한다. 따라서 generic low-level
ledger에 구조적으로 그럴듯한 receipt를 삽입해도 verifier 권한으로 승격되지 않는다.
이 recovery는 exactly-once delivery나 최초 응답 전달 성공을 의미하지 않는다.

Recovery는 동일한 exact current package/trust-registry/fixture-registry identity에서만
지원된다. Key rotation·revocation 또는 package registry 변경을 가로지르는 historical
trust snapshot 복원은 v1 범위가 아니며 registry drift는 fail-closed한다.

## Receipt와 기존 claim 보존

신규 durable receipt는 ledger ID/head, reservation/acceptance event, campaign/run,
release identity receipt hash, signed evidence receipt hash와 envelope identity를
결속한다. 이 신규 wrapper에서만 local durable replay claim이 `true`다.
여기서 `acceptance_commit_head_event_sequence`와
`acceptance_commit_head_event_hash`는 acceptance transaction 안에서 acceptance가
append된 직후의 historical commit-time head이며, receipt 반환 시점의 fresh global
head가 아니다. 다른 process가 이후 event를 append할 수 있으므로 current head가
필요하면 별도 audit receipt를 새로 발급해야 한다.

기존 v0.2.33 signed receipt의 `durable_replay_ledger_verified=false`와 v0.2.34
identity receipt의 `signed_envelope_binds_release_identity_receipt=false`는 그대로
유지한다. Ledger가 두 receipt를 나중에 join하는 것은 runner가 identity receipt
hash 전체에 서명했다는 뜻이 아니다.

후속 [signed release-identity binding v2](engine-v2-hip-fgmres-signed-release-identity-binding-v2.md)는
별도 v2 signature domain과 ledger namespace에서 이 결손을 닫는다. Full identity
receipt schema/hash를 challenge와 signed payload에 직접 넣고 v2 durable receipt까지
같은 hash chain을 보존한다. 본 v0.2.35 namespace/receipt를 재사용하거나 본 receipt의
false claim을 소급 변경하지 않는다.

## Claim boundary

성공한 신규 receipt에서만 true인 범위는 다음이다.

- 사전 구성된 단일 local ledger의 challenge/runner-sequence cross-process 재사용 차단
- ledger-issued challenge의 재시작 후 strict 복원
- fresh release artifact replay와 기존 signed/numerical verifier의 결합
- acceptance 성공 반환 전 SQLite EXTRA synchronous transaction commit
- canonical stored blobs, schema와 event hash-chain replay
- identity/signed receipt와 envelope의 local durable acceptance 결속

다음 claim은 계속 false다.

- exactly-once delivery, 자동 retry 성공 또는 무손실 abandoned-challenge recovery
- 다른 host나 다른 ledger instance 사이의 replay 방지 또는 cross-host consensus
- 동일 UID/root/storage administrator의 database 재작성·삭제·coordinated rollback 저항
- cryptographic transparency/authenticity ledger, TPM/remote monotonic anchor와
  at-rest authenticity
- NFS/FUSE/non-POSIX locking·fsync 및 controller의 거짓 sync에 대한 보증
- wall-clock authenticity, 물리적 fsync 완료가 TTL deadline 이전이었다는 시각 증명
- trust/key/fixture registry rotation을 가로지르는 historical recovery
- signed envelope 자체의 full release-identity-receipt hash binding
- hostile same-process/in-process mint isolation, runner honesty와 hardware-root
  attestation
- local verifier가 외부 GPU 실행을 독립 관찰했다는 claim
- 실제 external `gfx1100` parity: `0/10`
- same-artifact two-architecture, release promotion eligibility, ResultIR,
  iteration host-copy-zero
- kernel/solver speedup, end-to-end O(N), commercial readiness 또는 상용 인증

Package active key는 `0`이므로 공개 key 경로는 계속
`trust_anchor_not_found`로 fail-closed한다. 합성 key 기반 회귀는 ledger와 verifier
계약을 검증할 뿐 실제 hardware evidence가 아니다.

## 검증 결과

- low-level durable ledger focused suite:
  `tests/test_engine_v2_durable_replay_ledger_v1.py` — `41 passed in 13.65s`
- high-level HIP FGMRES replay-ledger focused suite:
  `tests/test_engine_v2_hip_fgmres_external_replay_ledger_v1.py` —
  `13 passed in 446.87s`
- 기존 external signed-evidence 전체 회귀:
  `tests/test_engine_v2_hip_fgmres_external_signed_evidence_v1.py` —
  `16 passed in 658.36s`
- release identity, wheel artifact, dependency closure, public API와 capability matrix
  지원 회귀: `104 passed in 2.42s`
- 위 네 비중복 실행의 publication validation bundle: `174 passed`
- 변경 Python Ruff check/format, `py_compile`과 두 신규 JSON Schema Draft 2020-12
  검사: 통과
- candidate wheel: `1112675` bytes, `209` members, uncompressed `5901360`
  bytes, `sha256:db284e292f22626d1f7e2e65b6fa494b1d55e790374e432bb1127efb22c3ba7f`,
  `RECORD` `sha256:72395e8712722d2b5ec6499996e3b08cdd14e837a063dcd463089046a5e02834`
- wheel에 신규 ledger 모듈과 두 receipt schema가 포함되고 private-key 표식은 없었다.
  Source tree 밖 system-site dependency 격리 venv에서 wheel을 `--no-deps`로 설치해
  공개 export/schema resource import, ledger 초기화·close·pinned reopen과 empty audit
  replay를 확인했다.

## 다음 순서

1. 격리 runner/HSM key 운영과 검토된 rotation/revocation 절차
2. 최종 candidate의 실제 external `gfx1100` fixed-suite `10/10` 서명 evidence
3. 동일 final artifact의 local `gfx1030` `10/10` 재실행
4. external monotonic anchor
5. iteration host-copy-zero gate
6. ResultIR integration
7. certificate-bound SPD-gated PCG 상태기계
