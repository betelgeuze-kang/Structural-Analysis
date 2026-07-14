# Engine v2 HIP FGMRES package fixture registry v1

- 상태: implemented, package-local replay gate
- 날짜: 2026-07-14
- 후속 working milestone: v0.2.34 external release identity v1; committed audit HEAD `b2284e7a640932f9e21f5d78ed141097c721d4dd`
- package registry resource 스키마: `structural-analysis-hip-fgmres-fixture-registry.v1`
- suite: `phase0_execution_plan_v2_linear_frame_truss_fgmres_fixed_suite.v2`
- evidence scope: `package_local_unsigned_non_promoting`

## 목적

이 계약은 Phase 0 FGMRES CPU/HIP 모델군 검증에 사용할 10개 입력을 테스트
디렉터리가 아닌 배포 패키지 안에 고정한다. 각 slot은 ModelIR 파일 이름이나 설명만
신뢰하지 않고 다음 전체 fingerprint로 등록한다.

1. package resource 원본 바이트 SHA-256
2. ModelIR canonical content hash
3. SolverModelBuffers에서 재생한 ExecutionPlan v2와 모델 descriptor
4. 명시적 FGMRES policy, free-space plan, FGMRES plan, recurrence plan
5. deterministic CPU FGMRES 결과, 종료 코드, 카운터, restart history
6. solution/true-residual raw data hash
7. FGMRES와 독립적인 작은 dense Gaussian-elimination 직접해와 residual hash
8. topology, support, 하중 위치, local-axis roll, analytic solution predicate

caller가 fixture 경로, slot label, architecture 또는 expected hash를 넘기는 공개 API는
없다. 공개 로더는 고정 package registry만 읽는다.

`HipFgmresFixtureRegistryResultV1.to_manifest()`는 검증된 process-local replay 결과를
요약하는 출력이며 위 package resource 스키마의 역직렬화 입력이나 외부 증거 receipt가
아니다. Typed result validator는 retained authority를 검사하고 package registry를 fresh
replay한다. 별도 replay-result schema가 생기기 전까지 이 summary를 serialized authority나
promotion 근거로 소비하지 않는다.

## 고정 케이스

| slot | 물리/수치 의미 | CPU 기준 종료 |
| --- | --- | --- |
| `frame_single_axial` | 단일 3D frame, N2 `FX=100000` | happy breakdown, 1 iteration |
| `frame_single_weak_axis_bending` | 단일 frame, N2 `FY=-10000` | happy breakdown, 2 iterations |
| `frame_single_strong_axis_bending` | 단일 frame, N2 `FZ=-10000` | happy breakdown, 2 iterations |
| `frame_single_torsion` | 단일 frame, N2 `MX=5000` | happy breakdown, 1 iteration |
| `frame_single_rotated_local_axis_bending` | skew geometry, roll `0.37`, global FY, `M=6,I=5` | max iterations, 5 Arnoldi columns |
| `frame_serial_later_column` | 3-node serial frame, later Arnoldi column 필요 | happy breakdown, 2 iterations |
| `truss_single_axial` | 단일 3D truss, 자유 DOF 1개 | happy breakdown, 1 iteration |
| `recurrence_initial_or_early_terminal` | 고정 N1에만 하중, free RHS exact zero | initial true-residual convergence, 0 iterations |
| `recurrence_later_restart_partial_final_cycle` | 5-node serial frame, `M=2,I=5` | max iterations, cycle widths `2,2,1` |
| `recurrence_exact_full_final_cycle_guard` | 동일 5-node model, `M=2,I=4` | max iterations, cycle widths `2,2` |

마지막 두 slot은 ModelIR 원본 바이트와 ExecutionPlan이 완전히 동일하다. 따라서 두
케이스의 구분은 cosmetic model ID가 아니라 policy, iteration count, restart history와
CPU result hash에만 의존한다.

## 무결성 경계

- registry resource 원본 바이트는 코드에 고정한 SHA-256과 일치해야 한다.
- registry 내부 canonical `registry_hash`와 각 `slot_registration_hash`를 다시 계산한다.
- UTF-8 BOM, duplicate JSON key, NaN/Infinity, schema 추가 필드, 누락 slot을 거부한다.
- model resource는 고정 package basename만 허용하고 읽은 동일 bytes를 hash 및 parse에
  사용한다.
- slot ID 순서, case fingerprint, registration hash는 모두 unique여야 한다.
- ModelIR를 실제 buffer/plan/solver chain으로 재생하지 못하면 등록 완료로 강등하지
  않고 전체 registry load를 오류로 종료한다.
- 기존 `model-family-parity.v1`의 역사적 `0/10`, `0/20` interlock은 변경하지 않는다.
  이 registry는 후속 `model-family-parity.v2`의 입력 권한이다.

현재 package registry hash는
`sha256:0f9fb841c2ed6bfe2aef43024d5a496485f06d3d00b95892c7304b7e0dab7eb6`,
replay receipt hash는
`sha256:c265bd5f8e465fa2605c5c56f78159656ef714647dfd2d098b3a747420d7c324`다.

## 검증 결과

- 신규 registry 집중 테스트: `11 passed in 25.00s`
- 역사적 model-family v1 회귀: `16 passed in 4.90s`
- CPU FGMRES + recurrence-plan 인접 회귀: `90 passed in 39.50s`
- wheel: `1009749` bytes,
  `sha256:b0dd44b98ae1c5932b15ef4b830392d2c70acb91e26c61c56130365026b425ec`
- wheel 내부 resource: model/registry JSON `11`, registry schema `1`
- source tree 밖 격리 venv wheel 설치 후 10 slot 전체 replay와 동일 registry/receipt hash 확인
- v0.2.33 external verifier 추가 wheel: `1034513` bytes,
  `sha256:4031426ee32b973e1e702f2947cc4dfebaaaf4be1f5d39043fabb11b5b7318e4`.
  Verifier는 이 current package registry와 schema manifest를 직접 재생하지만,
  caller-supplied expected wheel/source identity의 파일을 직접 다시 해시하지는 않는다.
- v0.2.34 [external release identity v1](engine-v2-hip-fgmres-external-release-identity-v1.md)
  local unpushed working milestone은 candidate wheel/설치본, clean Git/exact archive,
  runner/build/lock, runtime dependency wheelhouse와 declared recipe를 독립 재생한
  release binding에 이 registry identity를 결합한다. 이 후속 계약은 registry
  receipt 자체의 hardware/signed/promotion authority를 변경하지 않는다.

## Claim boundary

이 단계에서 true인 것은 package fixture 10개가 exact replay로 등록되었다는 사실뿐이다.
다음 claim은 모두 false다.

- registry receipt 자체의 실제 HIP hardware parity claim
- full model-family parity 또는 모든 frame/truss 지원범위
- multi-architecture 또는 same-process two-ISA parity
- registry receipt 자체의 서명 또는 release promotion
- external verifier package active key와 실제 `gfx1100` signed evidence
- atomic multi-artifact snapshot, build 실행/재현성, remote commit authenticity,
  build-system dependency closure, dependency 설치 실행/current-interpreter wheel-tag
  호환성, bounded total source-artifact memory와 durable replay ledger
- hostile same-process mint isolation, runner honesty, hardware-root attestation,
  same-artifact two-architecture
- iteration host-copy zero, ResultIR, speedup, end-to-end O(N), commercial readiness

## 다음 순서

후속 [model-family parity v2](engine-v2-hip-fgmres-model-family-parity-v2.md)가
actual local `gfx1030` 10/10을 별도 live receipt로 확인했다. Registry receipt에 그
hardware claim을 역으로 삽입하지 않는다. 남은 순서는 다음과 같다.

v0.2.33은 local receipt와 외부 증거를 섞지 않는 별도 trust-anchor signed verifier
계약을 구현했다. 합성 exact 10-slot 성공·공격 경로를 포함한 집중 `10 passed`와
quick suite `23 passed`는 계약 검증일 뿐 hardware evidence가 아니다. Package active
key가 `0`이므로 공개 verifier는 `trust_anchor_not_found`로 fail-closed한다.

v0.2.34는 실제 release artifact identity를 두 번 순차 replay하고
challenge·signed verification 앞 fresh replay하는 계약을 local branch에 추가했다.

1. identity receipt와 signed campaign/run sequence의 durable replay ledger
2. 검토된 external runner key·rotation/revocation policy와 격리 harness
3. 최종 artifact에서 외부 actual `gfx1100` 10개 cell 실행 및 서명 검증
4. 동일 final artifact에서 local `gfx1030` 10/10 재실행
5. 그 다음에만 iteration host-copy-zero → ResultIR → SPD certificate-bound PCG로 이동
