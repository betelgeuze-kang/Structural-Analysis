# PM Release Gate Milestones

- 기준일: 2026-06-16
- 목적: PM 판정 기준을 재현 가능한 release evidence gate로 고정한다.
- 산출물: `implementation/phase1/release_evidence/productization/pm_release_gate_report.json`
- blocker handoff: `implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json`

## 실행 명령

```bash
python3 scripts/materialize_ndtha_corrected_state_recompute.py \
  --ndtha-stress implementation/phase1/nonlinear_ndtha_stress_report.json \
  --out implementation/phase1/release_evidence/productization/nonlinear_ndtha_stress.corrected_state_recompute.json \
  --sidecar-out implementation/phase1/release_evidence/productization/ndtha_corrected_state_recompute_report.json \
  --recommended-residual-top-displacement-m 1.0 \
  --recommended-residual-drift-ratio-pct 2.0

python3 implementation/phase1/run_ndtha_residual_gate.py \
  --ndtha-stress implementation/phase1/release_evidence/productization/nonlinear_ndtha_stress.corrected_state_recompute.json \
  --max-residual-top-displacement-m 5.0 \
  --max-residual-drift-ratio-pct 10.0 \
  --recommended-residual-top-displacement-m 1.0 \
  --recommended-residual-drift-ratio-pct 2.0 \
  --max-fallback-rate 0.05 \
  --strict-recommended-residual-hard-fail \
  --require-corrected-state-recompute \
  --out implementation/phase1/release_evidence/productization/ndtha_residual_gate_report.json

python3 implementation/phase1/run_element_material_breadth_gate.py

python3 implementation/phase1/run_measured_benchmark_breadth_gate.py \
  --out implementation/phase1/release_evidence/productization/measured_benchmark_breadth_report.json \
  --worst-case-out implementation/phase1/release_evidence/productization/worst_case_report.json

python3 scripts/build_core_family_p95_report.py \
  --out implementation/phase1/release_evidence/productization/core_family_p95_accuracy_report.json

python3 scripts/build_solver_runtime_backend_policy.py \
  --output-json implementation/phase1/release_evidence/productization/solver_runtime_backend_policy.json

python3 scripts/build_pm_strict_ci_reports.py

python3 scripts/build_runtime_memory_release_budget_report.py

python3 scripts/build_opensees_roundtrip_trace_report.py --json

python3 scripts/build_ux_release_readiness_report.py --run-browser-smoke

python3 scripts/build_ai_orchestration_preflight_report.py \
  --out implementation/phase1/release_evidence/productization/ai_orchestration_preflight_report.json

python3 scripts/build_github_actions_ci_streak_evidence.py \
  --out implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json

python3 scripts/build_ci_consecutive_pass_manifest.py \
  --out implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json

python3 scripts/build_ci_streak_intake_packet.py \
  --out implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json \
  --out-md implementation/phase1/release_evidence/productization/ci_streak_intake_packet.md

python3 scripts/build_license_status_closure_report.py \
  --out implementation/phase1/release_evidence/productization/license_status_closure_report.json

python3 scripts/build_license_status_intake_packet.py \
  --out implementation/phase1/release_evidence/productization/license_status_intake_packet.json \
  --out-md implementation/phase1/release_evidence/productization/license_status_intake_packet.md

python3 scripts/build_frontend_dependency_audit_report.py \
  --out implementation/phase1/release_evidence/productization/frontend_dependency_audit_report.json

python3 scripts/build_ga_enterprise_readiness_report.py \
  --out implementation/phase1/release_evidence/productization/ga_enterprise_readiness_report.json \
  --out-md implementation/phase1/release_evidence/productization/ga_enterprise_readiness_report.md

python3 scripts/build_ga_enterprise_signoff_intake_packet.py \
  --out implementation/phase1/release_evidence/productization/ga_enterprise_signoff_intake_packet.json \
  --out-md implementation/phase1/release_evidence/productization/ga_enterprise_signoff_intake_packet.md

python3 scripts/build_paid_pilot_scope_guard_report.py \
  --out implementation/phase1/release_evidence/productization/paid_pilot_scope_guard_report.json \
  --out-md implementation/phase1/release_evidence/productization/paid_pilot_scope_guard_report.md

python3 scripts/report_pm_release_gate.py \
  --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json \
  --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md

python3 scripts/build_pm_release_blocker_action_register.py \
  --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json \
  --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md

npm run ai:preflight
```

## 현재 판정

현재 PM milestone gate는 `paid_pilot_candidate=true`, `limited_commercial_ready=true`, `ga_enterprise_ready=false`다.
다만 전체 PM release-area gate는 `release_area_gate_ready=false`, `full_release_gate_ready=false`이며 release area는 `12/14` green이다.

합격한 마일스톤:

- M1 Residual Release Hardening: release evidence 경로의 residual gate가 strict recommended hard-fail, fallback `0%`, `solver_raw_ratio=1.0`, normalized residual, corrected-state recompute `3/3`을 통과했다.
- M2 Core Engine Depth Closure: contact-material coupled case `31`, panel/contact failure `reason_code` `7`, nonlinear+residual same-case `3`이 같은 element/material breadth report에 명시됐다.
- M3 Strict Runtime Closure: NDTHA long profile, HIP e2e, CPU fallback 금지, device residency, host copy share가 통과했다.
- M4 Benchmark Breadth Expansion: measured breadth `304` cases, `22` families, family별 holdout, coverage-risk worst-case report가 통과했다. PEER/E-Defense blind prediction measured-response family `10` cases는 `peer_blind_delta=1/10`으로 별도 집계한다.
- M5 Commercial Packaging: viewer/reviewer surface, signed release registry, support bundle, validation/limitation manuals가 통과했다. 전용 manual은 `docs/release-validation-manual.md`와 `docs/release-limitation-manual.md`이며, support bundle의 redacted reviewer package에 함께 포함된다.
- Implementation orchestration: Cursor Agent와 OpenCode worker bridge preflight가 통과했다. 이 evidence는 release pass/fail을 대체하지 않으며, Codex가 goal tracking, diff review, verification, final acceptance를 계속 담당한다.

남은 M1-M5 milestone blocker는 없다.

전체 PM release-area blocker는 다음과 같다.

- Basic CI: local artifacts는 PR `2`회, nightly `230`회 연속 PASS를 보여주지만 release streak credit은 GitHub Actions tracked evidence를 요구한다. 현재 GitHub Actions PR/nightly streak evidence가 `0/30`이므로 두 lane 모두 `30`회 연속 PASS release evidence가 아직 없다.
- Security: SBOM/repro/secrets negative-start boundary는 통과하지만 license status closure report가 현재 `not_configured`를 막고 있다. `docs/templates/license_status.template.json`은 입력 형식 예시일 뿐 release evidence가 아니며, placeholder 그대로는 closure report가 hard fail한다.
- Security dependency audit: `frontend_dependency_audit_report.json`은 `npm audit --json` 결과를 release evidence로 고정하며 high/critical 및 total vulnerability가 `0`이어야 한다.

`pm_release_blocker_action_register.json`은 위 blocker를 owner action, acceptance criteria, 재현 command로 다시 묶는다. 이 register는 blocker를 해제하지 않으며, missing evidence를 release pass로 바꾸지 않는다.
`ci_streak_intake_packet.json`은 PR/nightly 30회 연속 PASS blocker를 닫기 위해 필요한 현재 streak, 부족 회수, GitHub Actions evidence 경로, 검증 command를 failure bundle에 고정한다.
`license_status_intake_packet.json`은 security blocker를 닫기 위해 제품/법무 승인자가 채워야 할 필드, 현재 blocker, 검증 command를 따로 고정한다.
`ga_enterprise_readiness_report.json`은 GA/Enterprise에 필요한 독립 V&V, family validation manual signoff, 고객 audit/failure bundle, support SLA evidence를 milestone/release-area gate와 분리해 owner handoff로 고정한다.
`ga_enterprise_signoff_intake_packet.json`은 GA/Enterprise 외부 signoff 3종이 채워야 할 필드와 evidence path를 고정하며, signoff evidence를 대체하지 않는다. GA readiness는 빈 `contract_pass=true`만으로 통과하지 않고 필수 필드, placeholder 부재, 승인 decision을 함께 확인한다.
`paid_pilot_scope_guard_report.json`은 constrained paid pilot에 필요한 검토 보조, 지정 구조군/workflow, engine/reviewer evidence package, unsupported/missing evidence blocker 문구와 evidence package artifact 존재를 검증한다.

최근 닫힌 release-area blocker:

- Strict CI: PM-scoped `require_ndtha`와 `require_hip` evidence가 `PASS`다.
- Runtime: explicit runtime/memory budget report 기준 p95 runtime budget exceed rate가 `0%`다.
- Memory: explicit OOM count `0` 및 peak memory budget report가 고정됐다.
- Interop: MIDAS/KDS roundtrip evidence와 OpenSees topology canonicalization/reload trace가 통과했다.
- Core engine: HF-vs-topk comparison row 기준 family별 core p95 accuracy report가 통과했다. high-noise robustness p95는 core p95 판정에서 제외하고 별도 robustness evidence로 유지한다.
- UX: automated browser rehearsal 기준 샘플 workflow가 30분 예산 안에 완료됐고, 기존 viewer review queue `7`건은 IFC load-model claim-scope 항목으로 분리됐다. 사람 대상 신규 사용자 관찰은 GA-strength evidence로 남긴다.

## Claim Boundary

현재 권장 범위는 제한된 paid pilot 또는 PM이 승인한 constrained commercial pilot이다. M1-M5 milestone은 Limited Commercial 후보 수준까지 올라왔지만, 전체 PM release-area gate가 막혀 있으므로 제품 설명은 다음 조건을 포함해야 한다.

- 구조 엔지니어 검토 보조
- 지정된 구조군과 지정된 workflow
- engine/reviewer evidence package 포함
- unsupported 또는 missing evidence 항목은 pass가 아니라 blocker로 표시

OpenSees evidence는 topology edge-list canonicalization과 exact JSON reload trace까지이며 full OpenSees solver execution roundtrip 주장은 아니다.

GA/Enterprise는 이 로컬 gate와 별개로 독립 V&V, family validation manual signoff, 고객 audit/failure bundle, support SLA evidence가 필요하다. 현재 `ga_enterprise_readiness_report.json` 기준 measured cases `304/300`, signed registry, support bundle은 통과하지만 독립 V&V, family signoff, 고객 audit/failure bundle/SLA evidence가 없으므로 `ga_enterprise_ready=false`가 맞다.
