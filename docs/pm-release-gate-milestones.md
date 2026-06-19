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

python3 scripts/build_ux_new_user_observation_report.py \
  --out implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json \
  --out-md implementation/phase1/release_evidence/productization/ux_new_user_observation_report.md

python3 scripts/build_ux_new_user_observation_intake_packet.py \
  --out implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json \
  --out-md implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.md

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

python3 scripts/report_release_evidence_freshness.py \
  --out implementation/phase1/release_evidence/productization/release_evidence_freshness_report.json \
  --out-md implementation/phase1/release_evidence/productization/release_evidence_freshness_report.md

python3 scripts/report_pm_release_gate.py \
  --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json \
  --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md

python3 scripts/build_pm_release_blocker_action_register.py \
  --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json \
  --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md

python3 scripts/build_pm_release_blocker_closure_board.py \
  --out implementation/phase1/release_evidence/productization/pm_release_blocker_closure_board.json \
  --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_closure_board.md

python3 scripts/build_pm_release_gate_completion_audit.py \
  --out implementation/phase1/release_evidence/productization/pm_release_gate_completion_audit.json \
  --out-md implementation/phase1/release_evidence/productization/pm_release_gate_completion_audit.md

python3 scripts/build_pm_release_gate_reviewer_handoff.py \
  --out implementation/phase1/release_evidence/productization/pm_release_gate_reviewer_handoff.json \
  --out-md implementation/phase1/release_evidence/productization/pm_release_gate_reviewer_handoff.md

python3 scripts/build_pm_owner_evidence_request_packet.py \
  --out implementation/phase1/release_evidence/productization/pm_owner_evidence_request_packet.json \
  --out-md implementation/phase1/release_evidence/productization/pm_owner_evidence_request_packet.md

python3 scripts/build_template_evidence_safety_report.py \
  --out implementation/phase1/release_evidence/productization/template_evidence_safety_report.json \
  --out-md implementation/phase1/release_evidence/productization/template_evidence_safety_report.md

python3 scripts/build_support_bundle.py

python3 scripts/report_pm_release_gate.py \
  --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json \
  --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md

npm run ai:preflight
```

## 현재 판정

현재 PM milestone gate는 `paid_pilot_candidate=true`, `limited_commercial_milestone_ready=true`, `limited_commercial_ready=false`, `ga_enterprise_ready=false`다.
다만 전체 PM release-area gate는 `release_area_gate_ready=false`, `full_release_gate_ready=false`이며 release area는 `12/15` green이다.

합격한 마일스톤:

- M1 Residual Release Hardening: release evidence 경로의 residual gate가 strict recommended hard-fail, fallback `0%`, `solver_raw_ratio=1.0`, normalized residual, corrected-state recompute `3/3`을 통과했다.
- M2 Core Engine Depth Closure: contact-material coupled case `31`, panel/contact failure `reason_code` `7`, nonlinear+residual same-case `3`이 같은 element/material breadth report에 명시됐다.
- M3 Strict Runtime Closure: NDTHA long profile, HIP e2e, CPU fallback 금지, device residency, host copy share가 통과했다.
- M4 Benchmark Breadth Expansion: measured breadth `304` cases, `22` families, family별 holdout, coverage-risk worst-case report가 통과했다. PEER/E-Defense blind prediction measured-response family `10` cases는 `peer_blind_delta=1/10`으로 별도 집계한다.
- M5 Commercial Packaging: viewer/reviewer surface, signed release registry, support bundle one-click export archive, validation/limitation manuals가 통과했다. 전용 manual은 `docs/release-validation-manual.md`와 `docs/release-limitation-manual.md`이며, CI/license source evidence와 함께 support bundle의 redacted reviewer package에 포함된다.
- Implementation orchestration: Cursor Agent와 OpenCode worker bridge 파일/CLI preflight가 구성되어 있고, OpenCode wrapper 기본 모델은 MiniMax M3 registry id `opencode-go/minimax-m3`다. Model availability evidence는 실행 환경의 writable `XDG_DATA_HOME` 계정 store에 의존하므로, sandbox가 `/tmp` fallback registry만 볼 때는 blocked로 남는다. 이 evidence는 release pass/fail을 대체하지 않으며, Codex가 goal tracking, diff review, verification, final acceptance를 계속 담당한다.

남은 M1-M5 milestone blocker는 없다.

전체 PM release-area blocker는 다음과 같다.

- Basic CI: local artifacts는 PR `2`회, nightly `230`회 연속 PASS를 보여주지만 release streak credit은 GitHub Actions tracked evidence를 요구한다. 현재 GitHub Actions PR/nightly streak evidence가 `0/30`이므로 두 lane 모두 `30`회 연속 PASS release evidence가 아직 없다. PR은 원격 `CI` workflow가 등록됐지만 tracked `pull_request` streak가 없고, nightly는 로컬 `.github/workflows/nightly-full-quality.yml` 파일은 있으나 원격 GitHub Actions registry에 아직 등록되지 않았다.
- Evidence Freshness: `release_evidence_freshness_report.json`은 `p0_closure_status.json`, `p1_readiness_status.json`, `p1_benchmark_breadth_status.json` 3개 core release evidence를 감사한다. 현재 3개 artifact 모두 `generated_at`, source commit, engine version, input checksum, reuse marker, producer mtime recency를 갖고 `3/3` pass한다. 이 gate는 heavy validation 재실행을 대체하지 않고, P0/P1 status receipt의 provenance/freshness를 release-area 증거로 고정한다.
- UX: automated browser rehearsal는 sample workflow가 30분 예산 안에 끝난다는 workflow evidence로만 인정한다. PM UX release-area pass는 실제 신규 사용자 human observation record, completion minutes, blocker count, observer, evidence reference, accepted decision이 들어간 `ux_new_user_observation_report.json.contract_pass=true`를 요구한다.
- Security: SBOM/repro/secrets negative-start boundary는 통과하지만 license status closure report가 현재 `not_configured`를 막고 있다. `docs/templates/license_status.template.json`은 입력 형식 예시일 뿐 release evidence가 아니며, placeholder 그대로는 closure report가 hard fail한다.

`pm_release_blocker_action_register.json`은 위 blocker를 owner action, acceptance criteria, 재현 command로 다시 묶는다. 이 register는 blocker를 해제하지 않으며, missing evidence를 release pass로 바꾸지 않는다.
현재 open blocker는 총 `5`개이며, CI/UX/Security 5개 모두 `external_owner_input_ready`로 분류된다. 이는 intake packet, acceptance criteria, reproduction/verification command가 준비됐다는 뜻이며, 실제 CI streak, human UX observation, product/legal license approval evidence를 대체하지 않는다.
`pm_release_blocker_closure_board.json`은 open blocker를 `external_owner_input_ready`, `local_remediation_ready`, `handoff_incomplete` closure state로 다시 묶는 PM daily board다. 이 board도 blocker를 해제하지 않으며, action register의 open blocker count와 handoff readiness가 support bundle에서 바로 확인되는지를 고정한다.
`pm_release_gate_completion_audit.json`은 PM release-area 15개와 M1-M5 세부 요구사항을 requirement-level row로 펼친다. 현재 audit는 milestone 세부 요구사항은 모두 pass, release-area 요구사항은 `12/15` pass, Basic CI/UX/Security 3개 top-level row가 external owner input ready 상태로 blocked임을 기록한다.
`pm_release_gate_reviewer_handoff.json`은 open blocker별 owner, closure state, reproduction/verification command, verdict-change condition을 reviewer package로 묶는다. 이 handoff는 reviewer가 어떤 evidence가 들어오면 판정이 바뀌는지 확인하는 산출물이며, CI streak, human UX observation, product/legal license approval evidence를 대체하지 않는다.
`pm_owner_evidence_request_packet.json`은 같은 open blocker를 owner별로 다시 묶어 owner가 제출해야 할 intake artifact, acceptance criteria, reproduction/verification command를 한 곳에 고정한다. 이 packet도 external evidence를 생성하거나 blocker를 해제하지 않는다.
`ci_streak_intake_packet.json`은 PR/nightly 30회 연속 PASS blocker를 닫기 위해 필요한 현재 streak, 부족 회수, GitHub Actions evidence 경로, 검증 command를 failure bundle에 고정한다.
CI streak intake는 `github_actions_ci_streak_evidence.json`의 schema, freshness, threshold, workflow active state, PR `pull_request` source, lane별 threshold pass를 다시 검증한다. 따라서 local artifact나 manifest-only 수정은 release streak credit이 아니며, source evidence가 blocked이면 intake도 hard fail한다.
`ci_consecutive_pass_manifest.json`과 `github_actions_ci_streak_evidence.json`도 support bundle에 함께 포함된다. intake packet은 owner handoff이고, source streak evidence가 없는 상태를 release pass로 바꾸지 않는다.
`license_status_intake_packet.json`은 security blocker를 닫기 위해 제품/법무 승인자가 채워야 할 필드, 현재 blocker, 검증 command를 따로 고정한다.
`license_status_closure_report.json`과 `docs/templates/license_status.template.json`도 support bundle에 포함된다. closure report가 실제 승인 evidence이고, template은 입력 예시일 뿐 release evidence가 아니다.
`ux_new_user_observation_report.json`은 신규 사용자 30분 sample workflow 관찰 evidence를 고정한다. observation source가 없거나 placeholder, slow completion, blocker count, 승인 decision 누락이 있으면 UX release-area blocker로 남는다.
`ux_new_user_observation_intake_packet.json`은 UX owner가 채워야 할 관찰 필드, `docs/templates/ux_new_user_observation.template.json`, 현재 blocker, 검증 command를 support bundle에 고정한다. UX template은 `template_only=true`와 `OWNER_INPUT_REQUIRED` placeholder를 포함하므로 그대로 observation evidence로 복사하면 hard fail한다.
`template_evidence_safety_report.json`은 `docs/templates/*.json` 전체를 스캔해 `template_only=true`, placeholder marker, pass signal 부재를 확인하고 license/UX/GA validator probe가 template copy를 evidence로 인정하지 않는지 고정한다. 이 audit은 template hygiene evidence이며, owner가 제출해야 할 실제 release evidence를 생성하지 않는다.
`support_bundle_manifest.json`은 redacted support bundle directory뿐 아니라 `implementation/phase1/release/support_bundle_export.zip`의 path, sha256, member count, archive roundtrip check를 고정한다. zip 자체는 ignored runtime artifact이고 manifest가 one-click export evidence다.
`ga_enterprise_readiness_report.json`은 GA/Enterprise에 필요한 독립 V&V, family validation manual signoff, 고객 audit/failure bundle, support SLA evidence를 milestone/release-area gate와 분리해 owner handoff로 고정한다.
`ga_enterprise_signoff_intake_packet.json`은 GA/Enterprise 외부 signoff 3종이 채워야 할 필드, owner별 packet, evidence path, source artifact, `docs/templates/*.template.json` template path를 고정하며, signoff evidence를 대체하지 않는다. GA readiness는 빈 `contract_pass=true`나 template copy만으로 통과하지 않고 필수 필드, placeholder 부재, 승인 decision을 함께 확인한다.
`paid_pilot_scope_guard_report.json`은 constrained paid pilot에 필요한 검토 보조, 지정 구조군/workflow, engine/reviewer evidence package, unsupported/missing evidence blocker 문구와 evidence package artifact 존재를 검증한다.

최근 닫힌 release-area blocker:

- Strict CI: PM-scoped `require_ndtha`와 `require_hip` evidence가 `PASS`다.
- Runtime: explicit runtime/memory budget report 기준 p95 runtime budget exceed rate가 `0%`다.
- Memory: explicit OOM count `0` 및 peak memory budget report가 고정됐다.
- Interop: MIDAS/KDS roundtrip evidence와 OpenSees topology canonicalization/reload trace가 통과했다.
- Core engine: HF-vs-topk comparison row 기준 family별 core p95 accuracy report가 통과했다. high-noise robustness p95는 core p95 판정에서 제외하고 별도 robustness evidence로 유지한다.
- Security dependency audit: `frontend_dependency_audit_report.json`은 `npm audit --json` 결과를 release evidence로 고정하며 high/critical 및 total vulnerability `0`으로 통과했다.
- UX workflow rehearsal: automated browser rehearsal 기준 샘플 workflow가 30분 예산 안에 완료됐고, 기존 viewer review queue `7`건은 IFC load-model claim-scope 항목으로 분리됐다. 다만 사람 대상 신규 사용자 관찰은 PM UX release-area pass 조건이라 닫힌 blocker가 아니다.

## Claim Boundary

현재 권장 범위는 제한된 paid pilot 또는 PM이 승인한 constrained commercial pilot이다. M1-M5 milestone은 Limited Commercial 후보 수준까지 올라왔지만, 전체 PM release-area gate가 막혀 있으므로 제품 설명은 다음 조건을 포함해야 한다.

- 구조 엔지니어 검토 보조
- 지정된 구조군과 지정된 workflow
- engine/reviewer evidence package 포함
- unsupported 또는 missing evidence 항목은 pass가 아니라 blocker로 표시

상용 v1 지원 범위 (commercial v1 supported scope): paid-pilot scope guard는 다음 항목이 scope source에 명시돼야 PASS다.

- frame structures, wall-frame structures, outrigger systems, truss systems (골조, 벽-골조, 아웃리거, 트러스 구조군)
- MIDAS interop, OpenSees interop, KDS interop
- nonlinear static, bounded NDTHA
- residual audit, reference comparison
- reviewer package (reviewer handoff package)

상용 v1 분리 검증 제외 (commercial v1 separate-validation exclusions): paid-pilot scope guard는 다음 항목이 scope source에 별도 검증 표기로 명시돼야 PASS다.

- rail/tunnel (철도/터널)
- special SSI (special soil-structure interaction, 특수 SSI)
- nonstandard contact (비표준 접촉)
- legal/authority approval automation (인허가 자동화)
- special construction stages (특수 시공 단계)

OpenSees evidence는 topology edge-list canonicalization과 exact JSON reload trace까지이며 full OpenSees solver execution roundtrip 주장은 아니다.

GA/Enterprise는 이 로컬 gate와 별개로 독립 V&V, family validation manual signoff, 고객 audit/failure bundle, support SLA evidence가 필요하다. 현재 `ga_enterprise_readiness_report.json` 기준 measured cases `304/300`, signed registry, support bundle은 통과하지만 독립 V&V, family signoff, 고객 audit/failure bundle/SLA evidence가 없으므로 `ga_enterprise_ready=false`가 맞다.
