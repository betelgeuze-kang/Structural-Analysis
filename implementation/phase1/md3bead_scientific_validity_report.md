# 3-Bead (CA-SC-CB) MD 기반 건축구조해석 정합성 리포트

## 0. 판정 요약
- **이론 판정:** 최소 포텐셜 에너지 관점에서 FEM과 MD는 동형(isomorphic) 구조를 갖는다.
- **모델 판정:** 3-Bead는 6-DOF(병진 3 + 회전 3)를 좌표 기반으로 표현하기 위한 최소 구성이다.
- **현재 구현 판정:** Python 참조모델과 Rust 훅의 수치 동치 검증이 통과했다.
  - `implementation/phase1/rust_md3bead_parity_report.json` -> `contract_pass=true`
- **주의:** "상용 FEM 완전 대체" 주장은 비선형 재료/경계/접촉 캘리브레이션 완료 전에는 과학적으로 확정할 수 없다.

## 1. 에너지 최소화 원리의 동형성
구조해석(FEM)과 MD는 모두 에너지 정지 조건을 푼다.

- FEM: 
  - 총 포텐셜 `Pi(u) = U(u) - W(u)`
  - 평형조건 `dPi/du = 0`
- MD:
  - 총 포텐셜 `V(r)`
  - 평형조건 `F = -grad(V) = 0`

선형 탄성 영역에서 FEM의 강성 기반 최소화와 MD의 포텐셜 최소화는 동일한 변분 구조를 갖는다.

## 2. 3-Bead가 필요한 이유 (6-DOF)
- 1-Bead: 점(3-DOF 병진)만 표현 가능
- 2-Bead: 선분 축 기준 회전 자유도 표현이 불완전 (비틀림 식별 한계)
- 3-Bead: 국부 평면/직교 기저 형성 가능 -> 휨/비틀림/워핑 항을 좌표 포텐셜로 표현 가능

따라서 CA-SC-CB는 beam-node의 6-DOF를 좌표계로 옮기기 위한 최소 자유도 구성으로 타당하다.

## 3. 구조 물성치 ↔ 포스필드 맵핑
- 축력 (bond stretch):
  - `V_bond = 0.5 * Kb * (r-r0)^2`
  - `Kb <-> E*A/L`
- 휨 (angle bend):
  - `V_angle = 0.5 * Ktheta * (theta-theta0)^2`
  - `Ktheta <-> E*I/L` (강축/약축 분리)
- 비틀림 (dihedral):
  - `V_dihedral = Kphi * f(phi-phi0)`
  - `Kphi <-> G*J/L`

## 4. 현재 코드 반영 상태
- 3-Bead SoA 물리루프:
  - `implementation/phase1/md3bead_soa.py`
- Step1/Step5에서 mock 제거 후 물리루프 연동:
  - `implementation/phase1/run_phase1_steps.py`
- Rust 동일 수식 훅:
  - `implementation/phase1/rust_hip_md3bead_hook/src/main.rs`
  - `implementation/phase1/rust_hip_md3bead_hook.py`
- Python-Rust 1:1 동치검증:
  - `implementation/phase1/validate_md3bead_rust_parity.py`

## 5. 비선형 Lennard-Jones 항복 맵핑 커널
- 구현:
  - `implementation/phase1/nonlinear_lj_hinge_kernel.py`
  - `implementation/phase1/validate_nonlinear_lj_mapping.py`
- 검증 계약:
  - 항복 검출(yield_detected)
  - 항복 변형률 정합(yield_strain_pass)
  - 항복 후 연화(post_yield_softening_pass)
  - 에너지 소산(energy_dissipation_pass)
- 결과:
  - `implementation/phase1/nonlinear_lj_mapping_report.json` -> `contract_pass=true`

## 6. 하드웨어 메모리 관점 (128MB 캐시)
- 분석 스크립트:
  - `implementation/phase1/three_bead_cache_budget.py`
- 기본 결과:
  - branches=10 -> 캐시 적합
  - branches=64 -> full batch 비적합, micro-batch 권장

## 7. 결론
- **정합성 관점:** 접근은 과학적으로 타당하다.
- **엔지니어링 관점:** 현재 구현은 "정합성 검증 가능 상태"이며, Rust 경로와 Python 참조모델 동치까지 확보했다.
- **남은 과제:** 상용 FEM 대비 최종 대체 주장에는 재료 비선형/접촉/경계 캘리브레이션과 대규모 benchmark 통계가 추가로 필요하다.
