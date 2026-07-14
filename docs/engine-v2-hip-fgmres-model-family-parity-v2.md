# Engine v2 HIP FGMRES registry-bound model-family parity v2

- 상태: implemented, local `gfx1030` fixed-suite lane complete; v0.2.34 release-artifact identity working contract available, external lane empty
- 날짜: 2026-07-14
- 감사 기준: pushed HEAD `b2284e7a640932f9e21f5d78ed141097c721d4dd`; v0.2.34 identity gate는 local unpushed working milestone
- 스키마: `structural-analysis-hip-fgmres-model-family-parity.v2`
- capability: `phase0_registry_bound_fixed_suite_live_hardware_coverage`
- evidence scope: `process_local_registry_bound_unsigned_non_promoting`

## 목적

이 계약은 [package fixture registry v1](engine-v2-hip-fgmres-fixture-registry-v1.md)의
exact 10개 slot만 actual HIP model-case 결과로 채운다. caller가 family label, fixture
path, expected hash, architecture requirement 또는 serialized external receipt를 제공할 수
없다. 공개 입력은 exact process-local `HipFgmresModelCaseParityResultV1` tuple 하나뿐이다.

각 live case는 다음 값이 registry slot과 모두 일치해야 한 matrix cell로 인정된다.

- ModelIR content와 authoritative ExecutionPlan descriptor
- ExecutionPlan, FGMRES plan, recurrence plan hash
- FGMRES policy와 deterministic CPU result/status/termination
- actual runtime architecture base와 compiled architecture
- device identity, runtime library, kernel identity와 kernel source
- terminal observation, solution, exported residual, independent residual replay를 이미 통과한
  single-case parity authority

한 architecture lane 안에서는 device ordinal/UUID/PCI, runtime library, kernel identity,
kernel source와 compiled architecture가 모두 같아야 한다. 같은 UUID/PCI를 서로 다른 ISA
base로 재표기하거나 같은 slot/architecture cell을 중복 제출하면 fail-closed한다.

Detached structural receipt validator도 fresh package registry identity, 각 observation의
slot registration/fingerprint/plan/policy/CPU/descriptor hash, logical case key와 matrix cell
ID, canonical order, duplicate cell/case, architecture device 일관성을 다시 계산한다. UUID와
PCI는 결합쌍이 아니라 각각 cross-ISA 재표기를 거부한다. 이 검증은 serialized consistency를
닫지만 process-local live authority를 복원하거나 외부 receipt를 matrix에 합산하지 않는다.

## Matrix 의미

고정 matrix는 package slot 10개 × architecture base 2개(`gfx1030`, `gfx1100`)의
20 cell이다.

- local actual `gfx1030`: `10/10` 완료
- external actual `gfx1100`: `0/10`; v0.2.33 signed verifier와 v0.2.34 independent artifact-identity working contract이 있지만 package active key는 `0`
- 전체 matrix: `10/20`

`gfx1030` 10/10은 아래 물리/재시작 경계를 포함한다.

1. single-frame axial
2. weak-axis bending
3. strong-axis bending
4. torsion
5. skew geometry + nonzero local-axis roll, 5 active Arnoldi columns
6. 3-node serial later-column convergence
7. single axial truss
8. exact zero free-space RHS initial convergence
9. 5-node `2+2+1` partial final cycle
10. 동일 5-node model의 `2+2` exact full-final-guard cycle

## 회전축 fixture counter-evidence

최초 hardware run은 회전축 fixture를 `M=6,I=6,rel=1e-12` happy-breakdown으로
등록한 상태에서 4분 13초 후 fail-closed했다. CPU/GPU final residual L2는 각각 약
`9.8325e-10`/`7.3293e-10`으로 두 값 모두 solver tolerance `1e-8`보다 작았지만,
near-zero residual vector와 norm의 기존 single-case absolute comparison `1e-12`를
통과하지 못했다.

역사적 single-case v1 허용오차를 완화하지 않았다. 동일 회전 모델을
`M=6,I=5,rel=1e-30` max-iteration operator case로 변경해 5개 active Arnoldi column을
검증했다. 격리 actual run에서 solution 최대 절대오차 약 `1.87e-16`, residual 최대
절대오차 약 `3.30e-10`으로 기존 상대오차 계약을 통과했다. 이 변경은 숨겨진 성공
승격이 아니라 fixture가 증명하는 수치 경계를 convergence가 아닌 operator/recurrent
parity로 명시한 것이다.

## 검증 결과

- fixture registry: `11 passed in 25.00s`
- family v2 unit/adversarial: `16 passed in 28.93s`
- historical family v1 freeze: `16 passed in 4.90s`
- registry + family v2 + historical family v1 aggregate: `43 passed in 55.34s`
- actual RX 6900 XT `gfx1030` 10-cell live aggregate:
  `1 passed in 1088.47s (0:18:08)`
- registry hash:
  `sha256:0f9fb841c2ed6bfe2aef43024d5a496485f06d3d00b95892c7304b7e0dab7eb6`
- registry replay receipt:
  `sha256:c265bd5f8e465fa2605c5c56f78159656ef714647dfd2d098b3a747420d7c324`
- wheel: `1009749` bytes,
  `sha256:b0dd44b98ae1c5932b15ef4b830392d2c70acb91e26c61c56130365026b425ec`
- wheel에는 fixture/registry JSON 11개, 신규 schema 2개, registry/family-v2 module
  2개가 포함된다. source tree 밖 격리 venv에서 registry 10개 replay와 empty v2
  non-promoting receipt를 확인했다.
- v0.2.33 verifier 추가 wheel: `1034513` bytes,
  `sha256:4031426ee32b973e1e702f2947cc4dfebaaaf4be1f5d39043fabb11b5b7318e4`.
  External signed verifier 집중 `10 passed`, registry/Ed25519/public API를 합친 quick
  suite `23 passed`를 통과했다. 이 합성 검증은 이 문서의 process-local family receipt에
  external cell을 추가하지 않으며 실제 external hardware evidence가 아니다.
- v0.2.34 [external release identity v1](engine-v2-hip-fgmres-external-release-identity-v1.md)
  working milestone은 candidate wheel/설치본, clean Git/exact archive/runner/build/lock,
  declared-target runtime dependency wheel closure와 declared recipe를 두 번 순차 replay하고
  challenge·signed verify 직전 fresh replay에 결속한다. 이는 v0.2.33의
  caller-supplied artifact identity 경계를 좁히지만 family receipt에 external cell을
  추가하지 않고 actual hardware evidence도 아니다.

`1088.47s`는 10개 GPU chain을 동시에 live로 유지하고 각 case authority 및 package
registry를 반복 재검증한 테스트 wall-clock이다. kernel/solver speedup 또는 제품
throughput benchmark로 사용할 수 없다.

## Claim boundary

현재 true인 제한된 claim은 다음뿐이다.

- exact package registry가 재생됨
- 제출된 10개 process-local single-case authority가 exact slot으로 분류됨
- local actual `gfx1030` fixed-suite 10/10 완료
- duplicate cell과 architecture/device identity drift 거부

다음 claim은 계속 false다.

- 모든 frame/truss 또는 full model-family parity
- `gfx1100` parity와 전체 20-cell 완료
- 일반적인 multi-architecture parity
- serialized external evidence를 이 process-local family receipt에 합산
- package active key와 실제 external signed evidence
- same-artifact two-architecture와 release promotion
- atomic multi-artifact snapshot, build 실행/재현성, remote commit authenticity,
  build-system dependency closure, dependency 설치 실행/current-interpreter wheel-tag
  호환성, bounded total source-artifact memory, identity receipt hash의 serialized signature binding
- hostile same-process mint isolation, durable replay ledger, runner honesty와 hardware-root attestation
- ResultIR, iteration host-copy zero, speedup, end-to-end O(N), commercial readiness

기존 historical `model-family-parity.v1`의 registered `0/10`, coverage `0/20`은
변경하지 않는다. v2의 새 증거를 v1 receipt에 소급 삽입하지 않는다.

## 다음 순서

1. v0.2.34 artifact identity receipt와 signed campaign/run sequence의 durable replay ledger
2. 검토된 external runner active key·rotation/revocation policy와 격리 runner harness
3. 최종 candidate artifact에서 독립 `gfx1100` 10개 cell 실행과 signature 검증
4. 동일 final key-bearing artifact에서 local `gfx1030` 10/10 재실행
5. 그 이후 iteration host-copy-zero gate
6. ResultIR integration
7. certificate-bound SPD-gated PCG state machine
