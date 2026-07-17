# Engine v2 HIP FGMRES reviewer-root registry v3 runner-key lifecycle

- Milestone: v0.2.56 unpublished candidate
- 기준일: 2026-07-17
- 구현 상태: `implemented`
- promotion 상태: `contract_only`
- detached constructed lineage reviewer / enrolled runner / active runner: `3 / 1 / 1`
- actual package reviewer / enrolled runner / active runner: `0 / 0 / 0`
- actual external `gfx1100` signed cell: `0/10`

## 1. 목적

v0.2.54 reviewer-root registry v3 genesis는 fresh lineage와 세 public reviewer root를
활성화하는 별도 `3-of-3` signature contract를 구현했지만 runner key count는
`0/0`으로 유지한다. 기존 key-enrollment v1은 runner private-key possession만 증명하고
어느 registry lineage에도 키를 등록하거나 활성화하지 않는다.

이 단계는 두 계약 사이의 실제 코드 공백을 닫는다. Exact registry-v3 genesis hash를
predecessor로 사용하는 v1 PoP challenge를 검증한 뒤 다음 두 전이를 구성한다.

1. registry epoch `2`: runner key enrollment
2. registry epoch `3`: enrolled runner key activation

두 전이는 각각 reviewer policy의 ordered unique `2-of-3` 이상 승인을 요구한다. 결과는
cryptographically self-contained detached receipt와 bootstrap source까지 다시 재생하는
attached result로 분리한다.

## 2. 전이와 hash chain

Enrollment statement는 다음을 exact copy한다.

- registry-v3 schema/ID, lineage generation/ID
- genesis event hash, registry hash, source registry receipt hash
- reviewer policy/root commitment와 세 public roots
- v1 PoP receipt/challenge hash
- runner/key/public-key identity
- `gfx1100`, fixture suite/registry, run-sequence, validity 범위
- runner-declared origin과 optional attestation digest

PoP challenge는 `predecessor_registry_epoch=1`, predecessor hash는 exact genesis registry
hash, `target_registry_epoch=2`, first key epoch `1`, predecessor key `null`이어야 한다.

Activation statement는 enrollment event와 epoch-2 registry transition hash를 predecessor로
사용한다. Activation 시각은 enrollment보다 strict-later이고 runner key의
`[valid_from, valid_until)` 안이어야 한다. 각 event hash는 statement와 reviewer approvals를
결박하고, registry transition hash는 lineage, epoch, predecessor registry hash, head event
hash와 immutable reviewer-root commitment를 결박한다.

## 3. Reviewer quorum과 signature 경계

Enrollment와 activation은 전용
`external-runner-key-registry-v3-review/v1` domain 아래 서로 다른 purpose와 statement
schema를 서명한다. 따라서 한 event의 signature를 다른 event로 재생할 수 없다.

- approval count: `2` 또는 `3`
- reviewer root set: 정확히 `3`, immutable source order
- approval order: `(reviewer_id, reviewer_key_id)` ascending
- duplicate reviewer/key: 거부
- event 시각: 각 reviewer root의 half-open validity 안
- key/signature: canonical non-identity prime-order Ed25519 검증

Product module은 message compile과 signature verify API만 제공한다. Private key loading,
key generation, signing API는 제공하지 않는다.

## 4. Detached와 attached 권한

Detached receipt는 포함된 registry-v3 receipt의 세 genesis signature, runner v1 PoP,
두 reviewer quorum event와 hash chain을 다시 검증한다. Outer schema는 자체 envelope를
`additionalProperties=false`로 검증하고, nested registry-v3와 enrollment-v1 object는 각
원본 strict schema/runtime validator를 transitive하게 실행한다.

Detached receipt 안의 root와 runner key가 임의의 synthetic ceremony에서 생성될 수 있으므로
package provenance 또는 운영 authority는 아니다. Attached result는 source registry-v3
result를 통해 bootstrap plan/receipt까지 재생하고 enrollment/activation statement를 source에서
deterministically 재구성해 exact equality를 요구한다. 이것도 package trust-store mutation이나
hostile same-process security boundary는 아니다.

## 5. Claim boundary

Detached constructed lineage의 `3 reviewer / 1 enrolled / 1 active`는 contract fixture의
cryptographic state다. 다음은 계속 false다.

- 실제 독립 reviewer root material 및 package inclusion
- package registry-v3 activation과 package runner enrollment/activation
- 실제 isolated runner process, HSM/hardware-token key, non-exportability attestation
- reviewer 인간/조직 identity, independence, HSM attestation
- trusted event clock, transparency log, monotonic anchor, historical resolver
- cross-host/cross-ledger replay prevention과 rollback resistance
- signed TraceIR, signed-evidence v3, durable-ledger v3
- actual external `gfx1100`, same-artifact two-architecture evidence
- ResultIR, broad iteration host-copy-zero, performance/speedup, end-to-end `O(N)`
- promotion eligibility와 commercial readiness

Synthetic private keys는 테스트에만 존재한다. `runner_declared_isolated_hsm` 문자열과
attestation digest는 검증되지 않은 metadata이며 실제 HSM claim으로 승격하지 않는다.

## 6. 복잡도

Reviewer 수는 policy상 `3`, approval 수는 `2..3`, lifecycle event 수는 이 contract에서
정확히 `2`로 고정된다. Hash/signature 검증과 receipt storage는 이 제한된 trust object에
대해 bounded다. FE 자유도 `N`, sparse operator, FGMRES iteration 또는 device transfer를
수행하지 않으며 solver end-to-end `O(N)`이나 speedup의 증거가 아니다.

## 7. 검증

- lifecycle numerical-independent/signature/adversarial unit contract: `22 passed`
- lifecycle unit/public + registry-v3 public: `26 passed in 34.97s`
- adjacent lifecycle/registry/bootstrap/enrollment/capability chain: `144 passed in 58.66s`
- strict outer Draft 2020-12 schema와 nested source/PoP validator replay
- ordered `2/3` quorum success, missing/duplicate/reordered/list/wrong-key rejection
- enrollment signature의 activation replay rejection
- foreign predecessor registry hash 및 attached bootstrap source substitution rejection
- strict event order와 runner key half-open validity boundary
- coherently rehashed package-activation/promotion claim과 bool/int alias rejection
- public symbols: Engine v2 `1152`, assembly backend `960`, solvers `66`, 각각 unique
- product source에 private-key 또는 signing API 없음

## 8. 다음 순서

1. 실제 세 독립 reviewer root bootstrap 및 registry-v3 genesis receipt를 reviewed package
   update로 포함한다.
2. 실제 isolated runner의 non-exportable HSM key로 v1 PoP를 발행하고 두 reviewer quorum
   event를 승인한다.
3. package-owned append-only registry resource와 historical resolver/monotonic anchor를
   구현해 detached state를 운영 authority로 승격한다.
4. 동일 release identity에서 actual external `gfx1100` `10/10`과 diagnostic TraceIR을
   signed-evidence v3 및 durable-ledger v3에 결박한다.
5. 동일 final key-bearing artifact를 local `gfx1030`에서 재실행한 뒤에만
   two-architecture evidence를 평가한다.
