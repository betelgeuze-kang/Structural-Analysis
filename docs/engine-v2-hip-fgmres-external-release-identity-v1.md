# Engine v2 HIP FGMRES external release identity v1

## 상태

- 로드맵 작업 마일스톤: `v0.2.34`
- 구현 및 pushed audit baseline: `7a46bfbd732e07291bc166ac6ff4266e1277e238`
- 작업 상태: pushed contract-only milestone
- 스키마: `structural-analysis-hip-fgmres-external-release-identity.v1`
- capability: `phase0_external_release_artifact_identity_replay`
- evidence scope: `local_double_replay_sequential_release_artifact_identity_non_promoting`
- package 활성 신뢰 키: `0`
- 실제 외부 `gfx1100` signed cell: `0/10`
- 승격 및 상용화 상태: `false`

이 문서는 v0.2.33 [external signed evidence v1](engine-v2-hip-fgmres-external-signed-evidence-v1.md)의 caller-supplied expected artifact identity
경계 앞에 실제 release artifact 재생 게이트를 추가한다. 후속 서명
검증은 검증된 artifact에서 파생한 기존 v1 release binding만 소비한다.
이 계약 자체는 외부 GPU를 실행하거나 release를 promotion하지 않는다.

## 목적과 연결 구조

```text
candidate wheel + installed distribution
clean Git tree + exact git archive + runner/build/lock files
dependency lock + dedicated runtime wheelhouse
declared build recipe
                       |
                       v
       independent identity replay, pass 1 and pass 2
                       |
                       v
 existing external-signed-evidence v1 release binding
                       |
                       v
       process-local verified-release capability
                  /                \
       fresh replay                 fresh replay
       before challenge             before signed verify
                  \                /
                   v              v
              v0.2.33 signed verifier
```

`compile_hip_fgmres_external_release_identity_v1` 내부에서 wheel, 설치본,
소스, source bundle, runner/build/lock role, dependency wheelhouse와 recipe를
두 번 순차 재생하고 동일성을 비교한다. Challenge 발급과 signed
evidence 검증 직전에도 보관한 경로 전체를 새로 재생한다.
다만 이는 순차적 동일성 게이트이며 여러 artifact의 atomic snapshot은 아니다.

## Candidate wheel과 설치본

Candidate wheel identity는 파일 이름을 증거로 신뢰하지 않고 다음을
fail-closed로 재생한다.

- no-follow로 연 같은 file descriptor의 bytes, inode/stat과 SHA-256
- wheel filename의 distribution/version/build/tag와 `METADATA`/`WHEEL` 일치
- absolute path, `..`, backslash, duplicate, NFC/casefold collision, symlink,
  encryption, unsupported compression과 고정 크기/압축 한계 거부
- 모든 ZIP member와 `RECORD` row의 exact member set, SHA-256, byte count
- `Requires-Dist`, `console_scripts`, `gui_scripts`의 canonical identity

현재 interpreter의 설치 distribution은 candidate와 name/version이 같고
`structural_analysis` import가 해당 distribution root를 가리켜야 한다. 설치본
`RECORD`를 candidate member와 다시 대조하고, wheel이 선언한 console/GUI
entry-point script를 설치 scripts root에서 별도 해시한다. 설치본에서
`RECORD`에 추가된 installer-created row는 신뢰하지 않고 bounded manifest로
receipt에 결속한다. 이 계약은 site-packages 전체 파일시스템 열거를 주장하지 않는다.

## Git 소스와 source bundle

Source identity는 top-level clean Git checkout에서만 발행된다.

- porcelain v2의 tracked, untracked, ignored, submodule drift가 모두 없음
- `HEAD`, object format, `ls-tree`와 index의 exact entry/mode/OID 일치
- `100644`/`100755` regular file만 허용하고 symlink, hardlink alias,
  unsafe/NFC/casefold-colliding path를 거부
- directory-FD/no-follow 읽기로 각 tracked file의 Git blob OID와 SHA-256 재계산
- raw `git archive --format=tar HEAD`와 source bundle의 byte-for-byte 일치,
  또한 tar member/content/mode 재생
- ordered runner-source aggregate, build recipe raw bytes, dependency lock raw bytes 해시

따라서 `source_commit`, tree manifest, source bundle, runner/build/lock identity는
caller가 제공한 expected string이 아니라 실제 checkout과 archive에서 파생한다.
그러나 이 계약은 해당 commit이 원격 저장소의 정당한 branch/tag에서 왔다는
remote authenticity를 증명하지 않는다. 개별 파일과 archive 크기는 제한하지만
tracked source 전체를 합친 process-memory 상한은 아직 계약하지 않으므로 bounded
source-artifact memory claim도 하지 않는다.

## Runtime dependency wheel closure

정규 canonical dependency lock은 고정된 target marker environment와 dependency
wheel row를 소유한다. 전용 wheelhouse는 lock에 있는 regular wheel만 정확히
포함해야 하며 symlink, 누락, 추가 artifact를 거부한다. 각 dependency wheel은
candidate와 동일한 wheel/ZIP/`RECORD` 검사를 받는다.

Root wheel과 dependency wheel의 canonical `Requires-Dist`, version specifier, marker,
requested extra를 target environment에서 재생해 exact reachable runtime graph,
direct/transitive 집합과 direct flag를 lock에 대조한다. 이는 runtime wheel
artifact closure이며 `pyproject.toml` build-system dependency, build isolation 환경,
실제 dependency 설치 실행을 증명하지 않는다. 여기서 target environment는 lock에
선언된 marker environment다. 현재 verifier interpreter가 그 환경과 같거나 candidate
wheel tag를 실제로 설치할 수 있다는 호환성까지 검증하지 않는다.

## 선언된 build recipe

Recipe는 strict canonical JSON으로 다음 정확한 policy를 선언해야 한다.

- policy: `isolated_pep517_verified_source_bundle_v1`
- frontend/backend: `pypa-build` / `setuptools.build_meta`
- argv: `python -m build --wheel --outdir dist .`
- fixed locale/timezone, `PIP_NO_INDEX=1`, dedicated wheelhouse,
  `PYTHONHASHSEED=0`, numeric `SOURCE_DATE_EPOCH`
- candidate wheel filename, dependency-lock SHA-256, target-environment hash
- `recipe_hash`를 제외한 canonical semantic hash

이 일치는 declared policy를 고정할 뿐이다. Verifier는 명령을 실행하지
않고, recipe가 candidate wheel을 생성했다거나 같은 소스에서 두 번의
bitwise-identical build가 나온다는 reproducibility를 증명하지 않는다.

## Receipt와 process-local capability

Release identity receipt는 wheel/installed/source/dependency/recipe identity hash와
주요 byte count, member/file/artifact count, manifest hash, 기존 release binding hash를
결속한다. `promotion_eligible`은 항상 `false`다.

성공한 compile은 직렬화된 receipt만으로 authority를 복원하지 않고,
공개 constructor로 정상 발행할 수 없는 process-local mint-guarded
verified-release capability에 입력 경로, 파생 release binding과 identity
receipt를 보관한다. Challenge 발급
직전과 signed-envelope 검증 직전에 전체 artifact를 fresh replay해
최초 identity와 다르면 거부한다. Signed verifier가 성공하면 identity
receipt와 signed evidence receipt의 같은 release-binding hash를 요구하는 별도
process-local combined capability를 발행한다.

Mint guard는 정상적인 공개 constructor 우회를 막는 process-local 불변식이지,
같은 Python process에서 임의 코드를 실행할 수 있는 적대자에 대한 격리 경계는 아니다.

현재 v0.2.33 envelope에 직접 서명되는 것은 검증된 artifact에서 파생한
기존 release-binding fields다. 신규 identity receipt hash 전체는 envelope의
serialized signed field가 아니며, combined capability도 process-local이지 durable
cross-process receipt가 아니다.

### v0.2.35 durable wrapper와의 관계

후속 [external replay ledger v1](engine-v2-hip-fgmres-external-replay-ledger-v1.md)은
명시 초기화한 단일 owner-private local POSIX SQLite ledger에 full
challenge, 본 identity receipt와 v0.2.33 signed receipt를 저장한다. Pinned
ledger ID/namespace, `synchronous=EXTRA` acceptance commit, strict canonical payload/schema
및 event hash-chain replay를 통해 프로세스 재시작 뒤에도 단일 ledger
내 cross-process at-most-once acceptance를 유지하고, commit 후 응답 전
crash는 recovery lookup에서 저장 시점 권위를 다시 검증한다.

신규 receipt의 `acceptance_commit_head_event_*`는 acceptance commit 시점의 head이자
acceptance event sequence/hash이다. 후속 event append 뒤의 current head를
증명하지 않으며, 후속 append는 이미 발행된 receipt를 stale로
만들지 않는다.

이는 본 identity receipt 자체의
`durable_replay_ledger_verified=false` 또는
`signed_envelope_binds_release_identity_receipt=false`를 바꾸지 않는다. Local
durable claim은 신규 v0.2.35 wrapper receipt에서만 true다. 따라서
ledger join은 full identity receipt hash가 runner envelope에 서명되었다는
뜻이 아니다. 또한 exactly-once, cross-host/multi-ledger, 동일 UID/root/storage
rollback 저항, cryptographic log/TPM anchor, non-POSIX/NFS/FUSE durability,
runner/hardware truth, 실제 external `gfx1100` 실행, promotion·ResultIR·
host-copy-zero·speedup·O(N)·commercial claim을 만들지 않는다. v0.2.35
pushed branch milestone에서 durable ledger `41`, high-level replay `13`, 본
signed-evidence `16`과 지원 회귀 `104`의 비중복 `174 passed`, candidate wheel
격리 설치·reopen audit를 완료했지만 이 claim 경계는 바뀌지 않는다.

## 검증 결과

- source/wheel/dependency identity, high-level double replay, public API/resource와
  capability matrix를 합친 최종 집중 실행: `133 passed in 3.21s`
- 신규 package schema manifest를 포함한 기존 external signed evidence의 raw
  10-slot 수치·공격 회귀: `10 passed in 466.28s`
- 변경 Python 모듈과 테스트 Ruff: 통과
- candidate wheel: `1078928` bytes, `205` members, uncompressed `5704400` bytes,
  `sha256:5f3349fbc0e9ac91c81ca0380e627f232f9df14f11a2c4b1ed9455e05a1389e5`,
  `RECORD` `sha256:42f8b30f308378fce6ff5afe2cfa5435b92d6b62855bbffd222f7d61eab9b646`,
  identity `sha256:65b1654c70a96a859ea0de2eb97e9ff26b2da68f0889761e4859a6c9fb4fe372`
- wheel은 `packaging>=23`, 신규 schema와 release/source/wheel/dependency identity
  모듈을 포함한다. Source tree 밖 system-site dependency 격리 venv에서 candidate
  member `204`, installer-created bounded extra `3`, declared console script `2`를
  다시 해시했다. Installed `RECORD`는
  `sha256:c45ac92f63a32df7d59cacb5b71ef11a7d002f59fcde2c536f0e4673e4e5e2f1`,
  두 번의 순차 replay hash는 모두
  `sha256:8ead4444769f4c4469d74fed3233f1c02f2efa12960cd1a2f5c167f7eccbaa23`다.
- 격리 venv에서 공개 API와 package schema resource import를 확인했다.
- wheel private-key 표식 검색 결과: 없음

위 결과는 local contract/package 회귀다. 실제 외부 runner, trust key, `gfx1100`
hardware 실행 또는 promotion receipt가 아니다. Lower-level artifact primitive는 실제
임시 artifact로 검사하고 high-level orchestration은 focused fixture/mocking 경계에서
검사했으므로, 하나의 production-like release 입력 전체를 사용한 end-to-end mint
실행 증거로도 승격하지 않는다.

## Claim boundary

성공한 이 local contract에서만 true인 claim은 다음이다.

- candidate wheel bytes/ZIP/`RECORD`와 installed distribution/declared script replay
- clean Git commit/tree/worktree/exact archive와 runner/build/lock raw identity replay
- exact declared-target-environment runtime dependency wheel closure
- exact declared build-recipe policy match
- 검증된 identity에서 기존 external release binding 파생
- challenge/signed verification 앞 fresh artifact replay의 process-local 결합

다음 claim은 계속 false다.

- atomic multi-artifact snapshot
- build recipe 실행과 build-system dependency closure
- reproducible build 및 remote commit authenticity
- runtime dependency 실제 설치 실행과 current-interpreter wheel-tag 호환성
- bounded total source-artifact memory
- identity-receipt hash 전체의 serialized signature binding
- hostile same-process mint isolation, runner honesty, hardware-root attestation,
  본 v0.2.34 receipt 자체의 durable replay ledger claim
- local process의 외부 GPU 실행 관찰
- 실제 external `gfx1100` parity: `0/10`
- same-artifact two-architecture, multiarchitecture completion, release promotion
- ResultIR, iteration host-copy-zero, kernel/solver speedup, end-to-end O(N)
- 상용 구조해석 제품 준비 및 commercial readiness

Package active key는 `0`이므로 public signed path는 여전히
`trust_anchor_not_found`로 fail-closed한다. 현재 local `gfx1030` family evidence는
historical unsigned `10/10`이며 이 working milestone에서 same-artifact로 재실행된
것이 아니다.

후속 [signed release-identity binding v2](engine-v2-hip-fgmres-signed-release-identity-binding-v2.md)는
본 receipt의 schema/hash를 별도 v2 envelope의 canonical Ed25519 서명 대상에 직접
포함한다. 이 후속 wrapper에서만 serialized identity binding claim이 true이며, 본
v0.2.34 receipt의 `signed_envelope_binds_release_identity_receipt=false`는 소급
변경하지 않는다.

## 다음 순서

1. 격리 runner/HSM key 운영과 검토된 rotation/revocation policy
2. 최종 candidate의 실제 `gfx1100` fixed-suite `10/10` 서명 증거
3. 동일 final artifact의 local `gfx1030` `10/10` 재실행
4. external monotonic anchor
5. iteration host-copy-zero 게이트
6. ResultIR integration
7. certificate-bound SPD-gated PCG 상태기계
