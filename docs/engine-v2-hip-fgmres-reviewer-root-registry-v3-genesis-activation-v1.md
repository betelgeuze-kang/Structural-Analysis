# Engine v2 HIP FGMRES reviewer-root registry v3 genesis activation v1

- Milestone: v0.2.54 unpublished candidate
- 기준일: 2026-07-17
- 구현 상태: `implemented`
- promotion 상태: `contract_only`
- package reviewer root / enrolled runner / active runner: `0 / 0 / 0`
- actual external `gfx1100` signed cell: `0/10`

## 1. 목적

v0.2.38 reviewer-root bootstrap 계약은 빈 trust-registry v2와 별도 lineage의 세
reviewer public root를 결박하고, 세 root 모두의 bootstrap-plan possession 서명을
검증한다. 그러나 해당 receipt는 target registry v3를 활성화하지 않으며 정책은 별도의
두 번째 `3-of-3` genesis activation 서명을 요구한다.

v0.2.54는 이 누락된 경로를 구현한다. Exact bootstrap plan/receipt를 source로 재생해
fresh registry-v3 genesis statement를 만들고, bootstrap 서명과 다른 domain에서 세
reviewer activation signature를 모두 검증한다. 결과는 detached registry receipt와
source bootstrap receipt를 함께 보유하는 attached result로 분리한다.

## 2. Fresh-genesis 경계

Registry v3는 v2의 append successor가 아니다.

- registry ID: `structural-analysis-engine-v2-external-trust-registry-reviewer-root-v3`
- schema: `structural-analysis-hip-fgmres-external-trust-anchor-registry.v3`
- lineage generation / registry epoch / event count: `1 / 1 / 1`
- predecessor registry ID/hash: `null / null`
- predecessor reviewer authority continuity: `false`
- reviewer roots: 정확히 `3`
- bootstrap/activation endorsements: 각각 `3-of-3`
- future registry event policy: `2-of-3`
- enrolled/active runner key: `0/0`

기존 empty v2 registry의 identity와 source-lineage commitment는 역사적 입력으로
결박하지만, v2에 존재하지 않았던 reviewer authority가 v3를 승인했다는 연속성은
주장하지 않는다.

## 3. Signature와 hash graph

1. Attached compiler가 bootstrap receipt 전체를 검증한다.
2. Bootstrap plan의 target registry ID, lineage ID, reviewer policy/root commitment를
   exact copy한다.
3. Activation 시각이 bootstrap 시각보다 strict-later이고 세 root의
   `[valid_from, valid_until)` 안인지 확인한다.
4. Genesis event hash는 bootstrap plan/receipt hash, source-lineage commitment,
   target lineage, policy와 root 전체를 canonical hash한다.
5. 세 reviewer는
   `reviewer-root-registry-v3-genesis-activation/v1` domain 아래 exact genesis를 서명한다.
6. Registry hash는 genesis와 ordered activation endorsements를 결박하고 receipt hash는
   claims와 빈 extensions까지 포함한다.

Ed25519 public key와 signature `R`은 canonical non-identity prime-order point를 요구하고
signature `S < L` 검사를 기존 evidence primitive에서 수행한다. Product module은 private
key 로딩 또는 signing API를 제공하지 않는다.

## 4. Detached·attached 권한 분리

Detached receipt는 포함된 세 public root 아래에서 exact genesis activation signature가
유효하고 bootstrap receipt hash가 commitment로 존재함을 검증한다. 임의의 세 key가
임의 bootstrap hash를 다시 서명할 수 있으므로 detached receipt만으로 package source
provenance를 주장하지 않는다.

Attached result validator는 원본 bootstrap receipt의 전체 signature/hash chain을 다시
검증하고, activation timestamp에서 genesis를 deterministic하게 재구성해 exact equality를
요구한다. 이 attached 결박도 process-local 검증 계약이며 package trust-store update,
운영 authority 또는 hostile same-process 보안 경계가 아니다.

## 5. Claim boundary

다음은 계속 false다.

- 실제 독립 reviewer root material과 package inclusion
- package registry-v3 activation 및 운영 reviewer authority
- reviewer 인간/조직 신원, 독립성, HSM origin/non-exportability
- trusted wall clock, transparency log, monotonic anchor, historical resolver
- isolated runner/HSM key enrollment 또는 activation
- signed TraceIR binding, signed-evidence v3, durable-ledger v3
- actual external `gfx1100`, same-artifact two-architecture evidence
- ResultIR, broad iteration host-copy-zero, performance, end-to-end `O(N)`
- promotion eligibility 또는 commercial readiness

Synthetic private keys는 테스트에만 존재한다. 해당 테스트 성공을 실제 reviewer ceremony,
HSM 또는 external hardware evidence로 재분류하지 않는다.

## 6. 검증

- detached/attached/signature/adversarial unit contract와 public schema/API: `20 passed`
- 신규 contract/public + v0.2.38 bootstrap + capability matrix: `91 passed in 23.74s`
- 기존 trust-registry v2 + key-enrollment 인접 회귀: `55 passed in 30.67s`
- exact-resource wheel isolated replay: `2 passed in 38.97s`; ResultIR v3 wheel 인접 `1 passed in 5.52s`
- public symbols: Engine v2 `1103`, assembly backend `930`, solvers `47`, 각각 unique
- Draft 2020-12 strict schema와 package resource 포함
- bool/int alias, missing/duplicate/reordered/list endorsements, wrong key/domain,
  bootstrap substitution, validity half-open boundary, promotion claim rehash를 fail-closed

## 7. 다음 순서

1. 세 실제 독립 reviewer가 분리된 keystore/HSM에서 root를 생성하고 bootstrap 및
   registry-v3 genesis 두 domain을 각각 서명한다.
2. 검토된 public roots/bootstrap/activation receipt를 명시적 package update로 포함한다.
3. v3 lineage에 묶인 isolated runner/HSM key enrollment와 reviewer quorum activation을
   구현·실행한다.
4. 동일 release identity에서 actual external `gfx1100` `10/10`과 diagnostic TraceIR을
   signed-evidence v3 및 durable-ledger v3에 결박한다.
5. 동일 final key-bearing artifact를 local `gfx1030`에서 재실행한 뒤에만
   two-architecture evidence를 평가한다.
