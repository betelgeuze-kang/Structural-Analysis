# Product Roadmap Closure Matrix

- Assessment date: 2026-07-22
- Base HEAD: `ab4b2e6191f87d9de9d117e2743d8f3fa4c9e50c`
- Assessment scope: uncommitted implementation candidate over the named base HEAD
- Authoritative release snapshot: **no**
- Overall closure: **blocked**

이 문서는 [제품 로드맵](repository-architecture-and-product-roadmap.md)의 PR 1-18을
현재 증거에 연결한다. `candidate_verified`는 로컬 working tree에서 focused test가
통과했다는 뜻일 뿐, merge, current-HEAD receipt 또는 release 승격을 뜻하지 않는다.
`partial`은 일부 구현이나 낮은 등급 evidence가 있다는 뜻이고 `blocked`는 필수 외부
입력 또는 권한 있는 증거가 없다는 뜻이다.

| PR | 상태 | 현재 근거 | 아직 필요한 폐쇄 조건 |
| --- | --- | --- | --- |
| 1 | `candidate_verified` | identity manifest, build metadata, API/CLI identity checker, `0.3.0` wheel candidate | committed HEAD에서 재검증한 build/receipt |
| 2 | `candidate_verified` | `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `CODEOWNERS`와 governance checker | 법률 담당자의 실제 제품 라이선스 승인; 현재 LICENSE는 권리 부여가 없는 보수적 경계 |
| 3 | `candidate_verified` | canonical capability registry와 README/API/CLI/Workbench generated surfaces | committed HEAD drift gate 실행 |
| 4 | `partial` | PR metadata validator, 2026-07-22 read-only GitHub re-inventory, current-tree blob audit; PR #162, PR #166 and PR #167 are merged | PR #137 metadata/disposition, authoritative age audit and authorized disposition of any branches found stale among 151 observed remote branches, 86 owner decisions with 3 release-surface dispositions, and 163 unapproved large history blobs |
| 5 | `candidate_verified` | bounded public core mypy PASS, 85% branch-coverage gate, 9-coordinate Python/OS CI and per-run current-HEAD snapshot artifact | committed clean-HEAD CI receipt; unpromoted nonlinear/research type debt remains outside the bounded gate |
| 6 | `candidate_verified` | typed numerical/engineering/nonlinear ResultIR plus hashed SI quantity catalog, JSON schema and absolute+relative comparison gate | committed clean-HEAD receipt; corotational binding remains PR 7-8 scope |
| 7 | `candidate_verified` | bounded portal compiler profile, replay-bound J1-J5 receipts, canonical hashes, schema and fail-closed validation | PR 8 exact recovery, PR 9 public API, PR 12-13 generalization, committed clean-HEAD receipt |
| 8 | `candidate_verified` | terminal-parent independent replay, SI quantity catalog binding, exact displacement/reaction/member/section/fiber recovery, immutable array hashes and tamper gates | PR 9 public API, external Level 2 comparison, committed clean-HEAD receipt |
| 9 | `candidate_verified` | one typed API/CLI envelope for fixed-chord and corotational profiles, normalized SI output, canonical schema/hash, full ancestry artifact and epoch-zero exact replay before resume | both Level 2 slots, general topology/load semantics, committed clean-HEAD receipt before product promotion |
| 10 | `candidate_verified` | element tangent가 COO triplet으로 직접 scatter되고 canonical sorted CSR로 coalesce되는 public corotational backend, deterministic pattern/numeric hashes, dense/sparse assembly 및 full-path SI 동등성, fallback 없는 CLI/API 선택 | committed clean-HEAD CI receipt; PR 11 factorization/conditioning diagnostics와 외부 V&V는 별도 gate |
| 11 | `candidate_verified` | public sparse Newton이 unregularized SuperLU/COLAMD를 사용하고 factorization별 schema/hash, exact 1-norm condition number, normalized pivot, backward error, fill, permutation, policy receipt를 남김; threshold 초과와 singularity는 fallback 없이 차단. 별도 experimental policy는 exact inverse-column solve를 블록화해 1536식까지 제한하고 실제 258식 3D graph solve에 연결됨 | committed clean-HEAD CI receipt; public exact scope는 계속 256식이며, experimental blocked-exact 진단은 제곱차수 작업이므로 production-scale estimator/policy·성능/메모리 receipt·외부 V&V는 별도 gate |
| 12 | `candidate_verified` | connected 2D graph compiler(2-128 nodes, 1-256 unique edges), branching-node receipt, arbitrary multi-node UX/UY/RZ constraints, load-factor-proportional prescribed displacement, prescribed-only no-solve commit, exact checkpoint/recovery/API/CLI path | committed clean-HEAD CI receipt; parallel members, disconnected graphs and non-proportional support history remain outside v1 |
| 13 | `candidate_verified` | finite-rotation global-XY rigid-arm map와 2차 접선, RZ release 내부좌표 국부평형과 Schur 소거, uniform initial-local dead-load consistent vector, dense/CSR parity, exact checkpoint/recovery/API/CLI 및 released-end net-moment gate; 직접 단일-DOF 변위 제어의 analytic load-factor column, dense/CSR, J1–J5, recovery, exact restart 경로 | committed clean-HEAD CI receipt; axial/shear/semi-rigid release, varying/partial/follower/thermal load, arc-length control과 외부 V&V는 별도 gate |
| 14 | `partial` | pinned OpenSeesPy 3.7.1.2 bytes were freshly executed against the current candidate; two-DOF modal, linear cantilever, fixed two-element elastic spatial-frame 3D, and whole-model consistent-mass modal/MAC comparisons pass on host and in a read-only-source/network-disabled same-operator container, with exact runtime/output/source/vector hashes and no reused execution | independent operator reproduction/attestation, public corotational nonlinear family breadth, normalization/tolerance review, legal posture and Level 2 operator promotion receipt |
| 15 | `partial` | pinned CalculiX 2.17-3 and dependency bytes were freshly executed against the current candidate; axial-member and whole-model repeated-mode linear-buckling/subspace comparisons pass on host and in a read-only-source/network-disabled same-operator container, with exact runtime/output/source/vector hashes and no reused execution | independent operator reproduction/attestation, broader frame/nonlinear comparison, normalization/tolerance review, legal posture and Level 2 operator promotion receipt |
| 16 | `candidate_verified` | implicit exponential traction–opening crack-band law with analytic tangent and energy-based characteristic-length scaling; seeded RC tie at 2/4/8 meshes has force-history and fracture-energy parity, deterministic state replay, zero fallback/regularization, schema and hashed generated receipt. 동일 law, asymmetric concrete, combined-hardening steel, confined-concrete envelope, perfect-bond composite와 condensed partial-interaction axial law가 stateful 3D 경로에 결합됨. 길이 방향 Gauss 적분 axial–biaxial fiber member 및 두 층 fiber section·connector quadrature·선형 slip field의 exact same-parent local Newton/Schur/checkpoint 경로도 제공함 | committed clean-HEAD receipt; production-scale distributed localization, general shear-lag/uplift/contact/connector-group mechanics, multiaxial constitutive breadth and published material/member validation remain separate gates |
| 17 | `candidate_verified` | SQLite WAL transactional state machine, content-addressed request/checkpoint/result/evidence blobs, hash-chained events, tenant/worker authorization, expiring leases, idempotent submission, HTTP-neutral API, Workbench read-only job projection, and an exact sparse portal prefix/reopen/resume comparison | committed clean-HEAD Python/OS and frontend CI receipt; production TLS/identity/rate-limit/SLO deployment and P3 multi-host distribution remain separate gates |
| 18 | `candidate_verified` | 서로 다른 물리 problem contract 3개를 calibration/validation/holdout으로 분리한 12개 exact-parent one-step replay, canonical outcome/evaluator/lineage hashes, feature·future-label 누수 차단, null-preserving coverage gate, holdout·안전·iteration-density 비회귀 scorecard가 `contract_fixture_pass`; `policy_gate_pass=false`, `retain_shadow_only`, 실행·결과 권한 없음 | committed clean-HEAD CI receipt; v1에는 signed independent-source attestation이 없으므로 독립 reviewed dataset/receipt 계약이 추가되어야 policy gate를 논의할 수 있고 guarded execution은 P3 범위로 계속 차단 |

## Phase status

| Phase | 상태 | 결정적 blocker |
| --- | --- | --- |
| P0 | `blocked` | PR/owner/history cleanup and committed clean-HEAD CI/readiness receipts |
| P1 | `blocked` | direct displacement-control and fresh two-solver technical candidates are locally verified; committed candidate receipt and both independently reviewed Level 2 slots remain |
| P2 | `blocked` | bounded material-point, small dense global elastic 3D/shear, native-sparse stateful 3D, a distributed axial–biaxial fiber member with steel/concrete/fracture-energy/confined section states, a single-mode condensed partial-interaction axial law, a separate two-layer fiber member with connector quadrature and a condensed linear slip field, a 258-free-equation blocked-exact sparse graph solve, local warping/imperfection, a fixed two-element same-operator OpenSees 3D technical comparison, sparse modal/buckling extraction, SDOF transient, durable job-service, non-promoting published Lee-frame numerical evidence, and a checksum-bound engineering-review/signature-verification handoff are locally verified; P1 closure, production-scale distributed localization, general shear-lag/uplift/contact/connector-group behavior, published material cyclic acceptance, independently reproduced and operator-approved Level 3 promotion, authoritative independently reviewed external 3D comparison, an authorized reviewer plus actual signed approval, and production deployment remain |
| P3 | `blocked` | P0-P2 prerequisites, external V&V, customer shadow evidence and production authorization |

## Latest candidate verification

이 결과는 working-tree 후보의 회귀검사이며 release evidence가 아니다.

- All 66 changed Python test files pass 667 tests in one integrated run after
  regenerating the checksum-bound unsigned engineering-review candidate.
- P0 governance/readiness suite: 195 passed; its smaller focused contract subset is 24.
- P1 corotational/API/sparse/member suite: 72 passed; the earlier focused subset is 48.
- P2 integrated candidate suite: 175 passed; the material/job/AI subset is 53 and the
  extended 3D/material/sparse/transient/Lee-frame grouping is 133;
  the bounded global 3D assembly/solve/recovery/checkpoint suite contributes 6/6 and
  passes focused mypy; the native-sparse axial-stateful 3D base suite contributes 7/7,
  the steel/concrete/confined/composite/partial-interaction adapter suite 9/9,
  the axial–biaxial stateful fiber-section suite 4/4, the distributed 3D fiber-member
  suite 5/5, the distributed two-layer connector-field suite 6/6, the actual
  258-equation graph suite 3/3 (including explicit rejection by
  the default 256-equation policy), and the blocked exact factorization suite 11/11;
  the combined 3D candidate grouping passes 60/60 and all 19 bounded P2 source files
  pass focused mypy;
  the Lee-frame formal candidate plus hierarchy contract suite passes 16/16, while the
  generated hierarchy result remains `intrinsic=false`, `promotion=false`, `highest=1`.
- P2 engineering-review package suite: 5 passed; 53 evidence files are byte-bound and
  the ephemeral trusted-key positive path verifies, while the checked-in registry remains
  empty and the stored candidate remains unsigned/non-promoting.
- P3 fail-closed entry-gate suite: 3 passed; `contract_pass=true` while
  `entry_gate_pass=false` and `p3_completion_pass=false` remain the intended result.
- bounded public-core suite: 114 passed, branch coverage 88% against the enforced 85% threshold,
  and mypy PASS on the declared public-core paths.
- Workbench production build and frontend build contract pass; all 6 non-listener job
  projection tests pass. The current full browser wrapper cannot bind `127.0.0.1` in this
  sandbox (`listen EPERM`), so its earlier 42-test observation is not counted as a current run.
- All 166 changed Python files pass Ruff. The package wheel
  `structural_analysis-0.3.0-py3-none-any.whl` builds offline, installs into an isolated venv,
  reports `structural-analysis@0.3.0`, contains 41 capability rows, imports the
  stateful/scalable 3D sparse, distributed fiber, biaxial section, confinement and
  partial-interaction plus distributed connector-field exports, and packages both checkpoint and scalable
  diagnostic schemas. Capability,
  fracture-energy, AI and P3 generated-artifact drift checks PASS; `git diff --check` PASS.
- OpenSees/CalculiX technical receipt: fixed external assets match all five pinned SHA-256
  values, both runtimes were freshly executed, all four cases and 22 numerical comparisons
  pass; the additional whole-model modal/buckling cases and binary mode-vector checks also
  pass. Both receipt suites pass 12/12. Their own claims still set Level 2, legal approval,
  redistribution approval, commercial equivalence and release readiness to `false`.
- container-isolated V&V candidate: read-only source, disabled runtime network, pinned base
  digest and stable derived image ID; 55 host/container scalar comparisons pass at
  `1e-12 + 1e-12 * scale`, and its offline contract suite passes 4/4. Exact buckling semantic
  hash parity is false and remains explicit; independent operator attestation is absent.

## Non-negotiable current blockers

- GitHub external state is read-only in this work: no PR close, merge, branch deletion or push
  has been authorized. The latest observation finds remote `main` at
  `86885920842ed92fdb638f10afc2d0ab3dc423ab`, six commits ahead of this
  candidate's base; PR #137 remains open, while PR #162, PR #166 and PR #167 are
  merged.
- The quarantine owner packet records `0/86` decisions and three release-surface-first
  dispositions still required. Owner identity, role, timestamp and evidence cannot be
  fabricated by implementation code.
- The current tree has no ordinary Git blob over 25 MiB, but the full published history has
  163 distinct unapproved blobs over the threshold. Rewriting and force-pushing published
  history is not authorized.
- OpenSees and a second independent solver have no promoted Level 2 receipts. Published
  Level 3, signed engineering review, legal approval, customer-shadow receipts and ROCm/HIP
  production proof are also absent.
- The Lee-frame fixed-mesh published-path comparison has a numerical `PASS` decision, but its
  candidate manifest explicitly retains missing publisher-source bytes, source-use approval,
  independent clean-runner reproduction, and formal operator approval. It receives no Level 3
  hierarchy credit and cannot bypass the missing Level 2 slots.
- The fresh OpenSees/CalculiX execution now has a same-operator container-isolated
  reproduction, but not an independent operator attestation or reviewed hierarchy submission.
  An independent reproduction and reviewed promotion package remain required for PR 14-15.
- The P2 engineering-review handoff now checksum-binds the exact evidence inventory and
  verifies trusted-reviewer Ed25519 assertions fail-closed. The trusted reviewer registry is
  intentionally empty and the candidate is unsigned, so `signed_engineering_review=false`
  remains authoritative.
- The candidate is uncommitted. The refreshed technical receipt records the base HEAD and
  checksum-binds the exact working-tree source bytes; it must be regenerated after an
  authorized commit to bind the resulting current HEAD.

Machine-readable companions are
[`artifacts/manifests/product_roadmap_status.json`](../artifacts/manifests/product_roadmap_status.json)
and the fail-closed
[`artifacts/manifests/p3_entry_gate.json`](../artifacts/manifests/p3_entry_gate.json).
