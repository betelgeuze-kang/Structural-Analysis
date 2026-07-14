# Engine v2 HIP FGMRES external signed evidence v1

## 상태

- 로드맵 마일스톤: `v0.2.33`
- 계약 버전: `v1`
- 구현 상태: verifier contract implemented
- 패키지 활성 신뢰 키: `0`
- 실제 외부 `gfx1100` signed cell: `0/10`
- 승격 상태: non-promoting

이 계약은 외부 `gfx1100` 실행기가 만든 FGMRES fixed-suite 증거를 기존
process-local model-family parity v2에 삽입하지 않고 별도 권한으로 검증한다.
현재 패키지 trust-anchor registry는 의도적으로 비어 있으므로 공개 verifier는
모든 봉투를 `trust_anchor_not_found`로 거부한다. 단위 테스트의 임시 키와 합성
봉투는 검증기의 성공·공격 경로를 검증할 뿐 실제 하드웨어 증거가 아니다.

## 신뢰 경계

신뢰 루트는 package resource의 Ed25519 공개키 registry와 이를 고정한 코드의
raw-byte SHA-256이다. 봉투는 공개키, PEM, certificate chain 또는 registry path를
제공할 수 없다. 제품 런타임 모듈과 wheel은 private-key material 또는 자체
signing API를 제공하지 않는다. 소스 배포본의 합성 검증 테스트는 일회성 임시
키를 메모리에서 생성해 성공 경로를 검사하지만 고정 private key/PEM/seed를
저장하지 않는다.

검증 성공이 의미하는 범위는 다음과 같다.

- package-owned active key와 runner/key epoch/run sequence가 일치한다.
- domain-separated Ed25519 서명이 exact canonical JSON payload를 보호한다.
- verifier가 발행한 32-byte 무작위 challenge가 request, campaign, audience,
  expiry, release binding과 결속되고 process-local에서 한 번만 소비된다.
- verifier가 전달받아 challenge에 고정한 expected wheel/source identity와,
  current package에서 직접 재생한 schema/fixture registry identity 및
  runner/runtime/kernel/device identity가 같은 signed payload에 결속된다.
- package registry의 canonical 순서대로 `gfx1100` 10개 slot이 정확히 한 번씩
  존재하고 family v2 detached receipt와 case receipt가 서로 일치한다.
- 각 case의 raw `solution_x`, `true_residual`, `solve_record` bundle hash를 다시
  계산하고 current package CPU FGMRES 결과 및 독립 `b-Kx`와 비교한다.
- current solve-record ABI, terminal status/code/counter/restart history/metric을
  기존 terminal observer와 동일한 detached decoder로 재생한다.

검증 성공만으로 다음은 증명되지 않는다.

- local process가 외부 GPU 실행을 직접 관찰했다는 사실
- hardware-root attestation 또는 악성 runner 부재
- durable/cross-process replay ledger
- local `gfx1030` lane의 서명 또는 동일 final artifact 재실행
- 기존 family v2에 external serialized evidence가 포함되었다는 주장
- full model-family, multiarchitecture release promotion
- ResultIR, iteration host-copy-zero, speedup, end-to-end O(N), commercial readiness

## 서명 바이트

입력 봉투 자체가 `canonical_json_bytes(parsed)`와 byte-for-byte 같아야 한다.
BOM, duplicate key, invalid UTF-8, NaN/Infinity, `-0.0`, whitespace와 key-order가
다른 표현은 서명 검증 전에 거부된다.

서명 메시지는 다음 domain과 canonical content의 연결이다.

```text
structural-analysis\0hip-fgmres-external-gfx1100-evidence\0v1\0
+ canonical_json_bytes({
    schema_version,
    capability_profile,
    algorithm,
    key_id,
    signed_payload_sha256,
    signed_payload
  })
```

공개키는 raw 32 bytes, 서명은 raw 64 bytes의 canonical standard Base64만
허용한다. `signed_payload_sha256`와 서명을 포함한 전체 envelope hash도 별도로
재계산한다.

## 릴리스와 실행 결속

`compile_hip_fgmres_external_release_binding_v1`은 다음 expected artifact를 현재
설치 package schema manifest 및 fixture registry와 결합한다.

- distribution name/version
- wheel filename/byte count/SHA-256/RECORD SHA-256
- source commit/tree/bundle SHA-256
- runner source/build recipe/dependency lock SHA-256
- 모든 packaged JSON schema의 ordered manifest hash
- fixture registry raw bytes/content/replay receipt hash

이 v1 verifier는 wheel 파일이나 source bundle 경로를 받아 직접 다시 해시하지
않는다. 따라서 wheel/source/runner/build/dependency 항목은 release operator가
사전에 계산해 verifier에 제공한 **expected identity**이며, 계약이 증명하는 것은
challenge와 서명이 그 expected identity를 byte-for-byte 보호했다는 사실이다.
현재 설치물에서 verifier가 독립 재계산하는 범위는 distribution version,
packaged schema manifest, fixture registry와 그 deterministic replay다. 독립적인
wheel/source manifest 생성·검증은 실제 runner 운영 및 승격 게이트에 추가해야
한다.

runner payload는 runner nonce와 sequence, started/completed UTC, exact `gfx1100`
architecture, device ordinal/UUID/PCI/name, ROCm/driver/HIPRTC version, runtime library
및 dependency manifest hash, kernel source/identity/code-object hash를 포함한다.

## 재생 방지

challenge 객체는 lock으로 `fresh -> reserved -> consumed`를 원자적으로 전이한다.
실패한 검증은 reservation을 해제하고 성공한 검증만 소비한다. 동시에 같은
challenge를 검증해도 하나만 reservation을 얻는다. 이 상태는 process-local이며
재시작 후 보존되지 않으므로 receipt의 `durable_replay_ledger_verified`는 항상
`false`다. 제품 승격 전에는 서명된 durable campaign/run-sequence ledger와 key
rotation/revocation 운영 절차가 별도로 필요하다.

## 외부 runner가 제출해야 할 자료

실제 runner는 최종 candidate wheel을 격리 설치한 뒤 다음을 한 봉투에 넣어야
한다.

1. verifier challenge와 exact release binding
2. package fixture registry identity
3. `gfx1100` common runtime/device/kernel binding
4. `gfx1100`만 포함한 detached family-v2 10-cell receipt
5. 각 slot의 full model-case receipt와 raw three-buffer completion payload
6. ordered per-case aggregate hash와 common runtime binding hash
7. broad/promotion claim이 모두 false인 고정 claims object

실제 key 등록은 공개키, runner identity, validity/revocation, run-sequence 범위와
exact fixture registry hash를 package trust registry에 추가하고 raw/schema hash를
검토하는 별도 변경으로 수행한다. 그 후에도 같은 최종 artifact의 local
`gfx1030` 10/10을 다시 실행하기 전에는 two-architecture same-artifact claim을
만들 수 없다.

## 검증

집중 테스트는 다음을 포함한다.

- RFC 8032 Ed25519 known-answer vector
- strict/canonical Base64와 canonical JSON
- package empty trust registry raw/content hash
- synthetic key로 signed `gfx1100` exact 10-slot happy path
- raw CPU solution/residual, independent residual 및 solve-record semantic replay
- wrong signature, whitespace, BOM, duplicate key, nonfinite JSON
- replay/concurrent reservation/expiry/wrong challenge
- slot reorder, raw payload mix, runtime/device mismatch
- 공개 empty-registry path의 fail-closed 거부

실제 외부 하드웨어 영수증은 아직 없으며 이 문서는 그 부재를 구현 완료로
재분류하지 않는다.
