# Codex 5.6 sol ultra 통합 로드맵

상태: `planning / non-promoting`

기준 시각: 2026-07-15 (Asia/Seoul)

이 문서는 `betelgeuze-kang/Structural-Analysis`의 현재 `origin/main`과 열린
PR #77, #78을 다시 관찰한 결과를 바탕으로 한다. 통합, readiness 또는
numerical closure 영수증이 아니다. PR #78은 merge 후보가 아니라 source
quarry이며, 아래 모든 통합 PR은 각 작업 시점의 최신 `origin/main`에서 새로
시작한다.

## 1. Verified baseline

### 1.1 Git 및 GitHub

| 항목 | 2026-07-15 재검증 값 | 판단 |
| --- | --- | --- |
| `origin/main` | `602dc8c0f0ce2c09e26b09540a8e67178cac32a3` | 제시된 관찰 SHA와 동일 |
| main 최신 커밋 | `Preserve authoritative evidence source ancestry (#76)` | protected evidence ancestry가 main의 명시 계약 |
| PR #77 | OPEN, draft, base `809f4ba5...`, head `e0bd0231...` | main 기반이 아닌 stack-internal slice |
| PR #77 GitHub 범위 | 1 commit, 23 files, `+861/-166` | 제시된 관찰값 유지 |
| PR #77 checks | `verify` 2개와 `frontend` 2개 모두 `CANCELLED` | green이 아니며 PASS로 해석 금지 |
| PR #77 main 직접 비교 | 317 ahead / 33 behind, merge base `7dd6bc6c...`; 1,019 files, `+869,402/-18,943` | current main 통합 후보가 아님 |
| PR #78 | OPEN, draft, base가 PR #77 head, head `8566a152...` | stack 후속 slice; 수정·rebase·merge하지 않음 |
| PR #78 GitHub 범위 | 18 commits, 145 files, `+70,317/-157` | 현재 stack base 대비 값 |
| PR #78 checks | `verify`, `frontend`가 queued/pending | 실행 완료나 PASS가 아님 |
| PR #78 main 직접 비교 | 335 ahead / 33 behind, merge base `7dd6bc6c...`; 1,133 files, `+939,563/-18,944` | salvage 분류의 보수적 기준 |

PR #78의 제시된 관찰값과 현재값 차이는 다음과 같다.

- head: `c4a055bd...` -> `8566a152...`
- main 대비 ahead: 329 -> 335
- main 직접 비교 files: 1,128 -> 1,133
- main 직접 비교 additions: 935,720 -> 939,563
- deletions: 18,944로 동일
- mergeable: `false` -> GitHub 현재 계산상 `true`, 단 merge state는
  `UNSTABLE`이고 rebaseable은 `false`
- base: 현재 PR #77 head branch로 설정되어 GitHub PR 화면 범위가 145개
  파일로 축소됨

`mergeable=true`는 아키텍처, numerical truth, provenance 또는 release gate를
통과했다는 뜻이 아니다. 두 PR 모두 main과 같은 merge base에서 33 commits
behind이며, 기존 branch를 직접 정리하는 대신 current-main source PR DAG로
재구성한다.

원래 작업 디렉터리는 PR #78 계열 branch에서 protected productization
evidence 수정과 untracked validation observation을 보유한다. 이 상태는
reset/clean하지 않았고, 신규 작업은 `origin/main`에서 만든 별도 clean
worktree에서 수행한다. clean worktree checkout 때 Git LFS binary 부재 및
기존 `.npz` pointer 경고도 관찰했으므로 LFS 재현성은 별도 mainline hygiene
위험으로 유지한다.

### 1.2 Readiness 및 numerical baseline

main의 canonical snapshot은 다음과 같이 읽혔다.

- `product_readiness_snapshot.json`: `status=stale_or_inconsistent`,
  `schema_valid=false`, `source_commit_sha=8c4f9ba3...`로 main tip과 불일치.
  해당 source SHA는 main ancestry 안에 있지만 snapshot 자체가 source-state
  conflict와 freshness 실패를 보고하므로 fresh closure evidence가 아님
- `blocker_count=119`: numerical 8, benchmark 5, software product 90,
  future commercial 16
- structural-scope owner decision pending 86, release-surface owner decision 3
- `release_ready=false`, `paid_pilot_ready=false`,
  `assisted_service_pilot_ready=false`, `solver_product_pilot_ready=false`,
  `limited_commercial_ready=false`, `ga_enterprise_ready=false`, 독립 상용 solver
  readiness도 false
- `workstation_delivery_ready=true`는 제한된 engineer-in-loop workstation
  delivery 표면만 가리키며 다른 gate를 승격하지 않음
- Developer Preview RC: `blocked`; deliverables 10/10, final gates 6/9.
  미폐쇄 gate는 selected medium models, 실제 Windows replay, human new-user
  observation
- G1 report: `dry_run=true`, 최고 보존 load factor 0.656 / required 1.0,
  terminal requirement 0/4, full-load child 미실행, HIP proof는 stale/preflight
  범위. 이 stored report가 관찰한 환경에는 `/dev/kfd`와 `/dev/dri`가 없었음

현재 Codex host를 별도로 확인하면 `/dev/kfd`, `/dev/dri`와 `rocminfo`의 local
`gfx1030` / AMD Radeon RX 6900 XT agent는 보이지만 `hipcc`는 없다. 이는 report
생성 당시 환경과 현재 local runtime의 차이일 뿐이며, G1 report를 fresh하게
만들거나 production/external hardware truth를 제공하지 않는다. R1은 HIP 코드를
변경하지 않으므로 hardware gate를 실행하지 않는다.

`.betelgeuze/intent_spec.md`, `.betelgeuze/project_contract.yaml` 및 두 protected
gap ledger의 관련 행도 대조했다. Commercial ledger는 G1의 남은 terminal
requirements를 full load, full mesh, material Newton breadth, production ROCm/HIP
residency 네 행으로 유지한다. AI ledger는 row-level guardrail/local closure와
`autonomous_ai_engine_claim_ready=false`를 동시에 유지하며, operator-attached
corpus와 external benchmark receipt를 proxy로 승격하지 않는다. 아래 DAG는 두
ledger가 요구하는 것처럼 gap 번호 순서가 아니라 dependency, local closability,
risk, evidence, verification 및 rollback 기준으로 재정렬한다.

`docs/commercialization-gap-current-state.md`의 blocker 41 및
`docs/github-documentation-status.md`의 과거 점수는 위 canonical snapshot과
drift되어 있다. 이 문서들의 숫자는 fresh readiness closure로 사용하지 않는다.
PR #78 문서의 Engine v2 v0.2.40/v0.2.41은 feature-branch/working-tree
milestone이며 main 포함, G1 closure 또는 readiness closure가 아니다.

## 2. Product 및 claim boundary

현재 허용되는 제품 경계는 conservative CPU structural API와 workstation
engineer-in-loop review assist, 그리고 좁은 local/process-scoped contract
observation이다. 다음 표현은 authoritative evidence가 생기기 전까지 금지한다.

- release-ready, paid-pilot-ready, independent commercial solver
- production HIP solver truth, G1 closed
- full-load 1.0 solved, full-mesh nonlinear equilibrium ready
- broad iteration host-copy-zero, end-to-end O(N)
- external gfx1100 parity complete
- autonomous AI structural engineer

Synthetic fixture, schema PASS, documentation PASS, test-double PASS, local
gfx1030 observation은 hardware-independent, external, commercial 또는 numerical
closure evidence가 아니다. Fallback, regularization, dry-run, stale source SHA,
missing hardware와 human/owner input은 항상 결과 옆에 남긴다. UI, security,
signed receipt는 G1의 physical residual/Jacobian/equilibrium chain을 대신 닫지
않는다.

## 3. Repository domain map

| Domain | 주 경로 | 통합 원칙 |
| --- | --- | --- |
| Structural product core | current main의 `src/structural_analysis` 보수적 API, model, analysis, solver | public contract와 numerical truth를 우선; unsupported는 fail-closed |
| Engine v2 quarry | PR #78에만 있는 `src/structural_analysis/engine_v2`, 관련 schemas/tests/docs | main에 존재하는 것으로 해석하지 않고 E0-E3의 한 contract 단위 PR로 재구현/추출 |
| ModelIR/MIDAS | current main의 legacy `io/midas`와 PR #78의 `model_ir`, MIDAS v2 additions, Execution/State/Result IR을 구분 | strict schema, loss audit, migration 및 compatibility test 필수 |
| G1 numerical lane | current main의 legacy phase1 G1 경로와 PR #78의 `assembly/g1_contract.py` 등 신규 quarry | E lifecycle과 분리; residual/Jacobian/material/globalization 순서 고정 |
| Generated/protected evidence | `implementation/phase1/release_evidence`, readiness snapshots | source PR 금지; source merge 후 별도 generated-only branch |
| Frontend legacy surface | `src/App.tsx`, `src/workbench`, repository-internal links | W lane에서 public manifest/allowlist로 축소 |
| Workbench v2 | `src/workbench-v2`, frontend tests | honest reader 기반; default surface 여부는 ADR/owner 결정 |
| Structure viewer | `src/structure-viewer` | Pages 공개 자산 inventory와 allowlist 검증 후 배포 |
| CI/release operations | `.github/workflows`, release scripts | R4/R6/V로 ownership, authorization, evidence ancestry 분리 |
| Quarantined non-structural | current main에서 quarantine된 86 paths와 PR #78에만 있는 `operator_attached`/추가 docking·GPCR·MD·science quarry를 구분 | structural product DAG 밖을 유지하고 owner 결정 뒤 별도 repo/plugin으로 extract 검토 |

main 관찰상 `src/structural_analysis`의 보수적 core는 6DOF frame/truss linear
static dense/SciPy sparse와 제한된 nonlinear preview를 제공한다. `ModelIR v2`,
HIP residency, FGMRES lifecycle, signed trust 및 대규모 phase1 generator 묶음을
동일한 public product surface로 취급하지 않는다.

## 4. PR topology와 merge 정책

```text
latest origin/main
  |-- R1 -- future clean-install consumers
  |-- R2
  |-- R3 -- W
  |-- R4 -- E*/W scale-out
  |-- R5 -- E0 provenance/ResultIR
  |-- R6 -- E3/V publication
  `-- R7 -- STOP until owner decisions

R1 -> R5/E0 contracts -> CPU oracle -> E1 resident HIP
   -> E2 lifecycle/family parity
        |-> G1 physical closure -> V fresh evidence
        `-> E3 external trust (parallel after E2; R6 before publication)
```

모든 신규 source PR은 최신 `origin/main`에서 독립 시작하고, 가능하면 25 files
이하 및 net 2,000 lines 이하를 지킨다. 일반 source PR에는 squash merge를
제안한다. Source merge 후 생성하는 evidence-only PR은 ancestry가 검증 계약이면
regular merge가 필요할 수 있다. 이 로드맵은 merge를 수행하거나 승인하지
않는다.

첫 PR은 R0 planning artifacts를 비규범적 기록으로 포함하되 public runtime
contract 변화는 R1 하나만 소유한다. Engine v2, G1, readiness producer,
generated evidence, frontend와 workflow는 변경하지 않는다.

## 5. PR #78 salvage strategy

PR #78의 main 직접 비교 1,133 files를
`docs/engineering/engine-v2-pr-salvage-map.json`의 28개 family에 전부 배정했다.
분류 합계는 1,133이며 unclassified는 0이다.

| 분류 | files | 처리 |
| --- | ---: | --- |
| `integrate_now` | 0 | PR #78에서 직접 가져올 즉시 통합 변경 없음 |
| `integrate_later` | 422 | E0-E3/G1 및 structural benchmark producer의 선행 계약에 맞춰 최소 단위로 재작성 또는 선택 추출 |
| `generated_evidence_only` | 411 | source merge 뒤 clean evidence branch에서 authoritative producer로 재생성 |
| `quarantine_or_extract` | 249 | docking/GPCR/MD/science domain을 structural product 밖으로 유지 |
| `superseded_or_discard` | 3 | divergent root package metadata whole-file 상태를 폐기하고 current main에서 재해결 |
| `owner_decision_required` | 48 | readiness/release ownership 결정 전 통합 중지 |

금지되는 방식은 PR #78 merge, rebase, broad cherry-pick, whole-directory copy,
generated evidence와 source의 동시 반입이다. 각 salvage PR은 candidate file의
최종 내용만이 아니라 main 대비 public contract, migration, numerical oracle,
fallback, hardware gate, provenance를 다시 검토한다.

## 6. Mainline hygiene backlog

### R0 — topology와 salvage map

- 본 로드맵과 exhaustive family classification 유지
- PR #77/#78은 read-only quarry로 고정
- baseline이 바뀌면 SHA와 counts를 재검증하고 차이 기록

### R1 — runtime dependency metadata parity

- `pyproject.toml`, `setup.cfg`, `requirements.txt` required dependency set을 동일화
- clean requirements install과 package/sparse solver import로 실제 runtime 경로 검증
- PR #78 metadata는 SciPy 누락이 남으므로 가져오지 않음

### R2 — CLI output collision과 atomic write

- `--out == --report-out`를 write 이전에 거부
- temp write, flush/fsync, atomic replace, failure rollback 계약
- Windows replace semantics와 기존 CLI compatibility test 포함

### R3 — Pages public artifact manifest와 link check

- repository-internal hardcoded link를 versioned public manifest로 이동
- allowlist asset만 `dist`에 복사
- private/customer/raw/operator/signature/zip 원본 배포 금지
- every link target build-time existence test 및 CI-ephemeral Pages inventory check.
  보존할 inventory receipt가 필요하면 source merge 뒤 V generated-only PR에서 생성

### R4 — Python/frontend CI path ownership

- Python-only, frontend-only, shared-contract path를 명시
- CI에서 불필요한 Node/Playwright 또는 Python setup 제거
- workflow contract에서 세 시나리오의 trigger ownership 검증

### R5 — source byte hash와 canonical solver-input hash

- 원본 bytes identity와 normalized solver-input identity를 별도 필드로 전파
- whitespace/source-only 변화와 semantic 변화의 hash 동작을 compatibility test로 고정
- Result/Validation public schema 변경에는 migration note 포함

### R6 — release/deploy authorization

- protected environment, approved actor/ref, branch/source SHA 조건 추가
- manifest commit/push, Pages, release publish를 각각 fail-closed authorization으로 분리
- dispatch 가능성 자체를 release 승인으로 해석하지 않음

### R7 — governance owner decisions

- root `CODEOWNERS`, `SECURITY.md`, `CONTRIBUTING.md`, license 정책 결정
- structural-scope 86건과 release-surface 3건의 human owner receipt 확보
- owner 결정 전 자동 생성으로 빈칸을 PASS 처리하지 않음

추가 mainline hygiene로 Git LFS clean-checkout 재현성과 tracked pointer 상태를 별도
PR에서 점검한다. 현재 R1에 LFS 파일을 stage하거나 갱신하지 않는다.

## 7. Engine v2 dependency DAG

### E0 — portable foundation

각 화살표를 독립 public-contract PR로 취급한다.

```text
ADR 001-007
  -> ModelIR v2 strict schema/validator/golden fixtures
      -> MIDAS v2 lexer/adapter/loss audit
  -> SolverModelBuffers + ExecutionPlan/StateIR/ResultIR
      -> CPU reference sparse operator
          -> CPU FGMRES oracle
```

E0는 CPU numerical oracle과 provenance vocabulary를 고정한다. AI proposal은
engineer-in-loop proposal/rollback contract만 소유하며 solver truth를 쓰지 않는다.

### E1 — HIP foundation

```text
context/device identity
  -> allocation lineage
  -> device assembly + resident CSR
  -> free-space plan/operator
  -> Krylov primitives
  -> actual hardware-gated CPU/HIP parity
```

Local static/schema/test-double gate와 actual ROCm device gate를 별도 check로 둔다.
`/dev/kfd`, `/dev/dri`, exact architecture/driver/runtime identity와 fallback-zero
receipt가 없는 환경에서는 hardware 결과를 SKIP/BLOCKED로 기록한다.

### E2 — FGMRES lifecycle

```text
plan/ABI
  -> RTC
  -> live checkpoint context
  -> canonical predecessor
  -> checkpoint atomicity
  -> sealed transaction
  -> global recurrence
  -> recovery
  -> FINAL_GUARD
  -> completion export
  -> terminal observer
  -> single-model parity
  -> fixture registry
  -> family parity
```

각 milestone은 하나의 ABI/schema/lifecycle 변화만 소유한다. PR #78의 누적
v0.2.x commit을 그대로 cherry-pick하지 않고 source, schema, focused tests와
bounded docs를 최소 집합으로 다시 구성한다. Completion export 또는 observer는
full solution/equilibrium/parity claim이 아니다.

### E3 — external evidence/trust

```text
signed evidence
  -> verified release identity
  -> durable replay ledger
  -> signed release-identity binding
  -> trust-anchor lifecycle
  -> reviewer-root bootstrap
  -> host-transfer audit
  -> family composition
```

Synthetic keys, repository fixture registry, local ledger와 local gfx1030 observation은
independent reviewer root, HSM ceremony, external gfx1100 parity를 대신하지 않는다.
Release identity publication은 R6 authorization을 선행 조건으로 둔다.

## 8. G1 closure lane

G1은 다음 numerical chain을 순서대로 닫는다.

```text
physical residual ownership
  -> same-state consistent Jacobian/JVP
  -> material state consistency
  -> globalization with explicit fallback/regularization
  -> full load 1.0 accepted replay
  -> full-mesh nonlinear equilibrium
  -> material breadth
  -> production HIP residency/parity
  -> fresh terminal evidence
```

각 단계는 같은 residual 정의, accepted state, load step 및 material state를
공유해야 한다. 현재 0.656 checkpoint, dry-run 및 0/4 terminal은 다음 단계의
입력 후보일 뿐 closure가 아니다. customer shadow 0/3, external benchmark 0/4,
independent V&V와 production HIP runner는 코드로 가짜 종료하지 않는다.

## 9. Workbench lane

- R3의 manifest/allowlist를 선행한다.
- `App.tsx`의 `implementation/phase1/release/**`, zip, signature, raw/operator
  hardcoded 경로를 공개 manifest lookup으로 교체한다.
- Pages에는 public allowlist asset만 복사하고 private/customer/raw/operator
  artifact는 포함하지 않는다.
- Workbench v2를 기본 표면으로 할지는 ADR과 product owner 결정으로 남긴다.
- 모든 링크는 build-time existence check와 browser navigation test를 통과한다.
- Workbench의 PASS, badge, signature 표시가 numerical 또는 release gate를
  승격하지 않도록 honest-reader semantics를 유지한다.

## 10. CI, release 및 evidence lane

- R4에서 CI path ownership과 runner policy를 분리한다.
- R6 전에는 manual dispatch라도 release/deploy를 승인된 것으로 보지 않는다.
- 각 source PR merge 뒤 최신 main의 clean checkout에서 authoritative producer를
  실행한다.
- producer source SHA가 history에 있고 input checksum이 일치하는지 확인한다.
- generated-only evidence PR에는 source implementation을 넣지 않는다.
- stale evidence는 source PR에서 임의 갱신하지 않고 blocker로 유지한다.
- customer/human/hardware/external/legal receipt는 해당 owner/환경에서만 생성한다.

## 11. Planned PR table

| PR | Public contract owner | 주요 선행 | 예상 merge 제안 |
| --- | --- | --- | --- |
| R0 | topology/salvage planning only | verified baseline | R1 draft에 non-normative docs로 포함 |
| R1 | required runtime dependency parity | latest main | squash |
| R2 | CLI two-output atomicity | latest main | squash |
| R3 | Pages public artifact manifest | latest main | squash |
| R4 | CI path ownership | latest main | squash |
| R5 | two-hash provenance | schema migration plan | squash |
| R6 | release/deploy authorization | owner policy | squash |
| R7 | governance files/decisions | legal/security/owner input | STOP until approved |
| E0-ADR | ADR 001-007 only | R0 | squash |
| E0-ModelIR | ModelIR v2 schema/validator | ADR, R5 | squash |
| E0-MIDAS | MIDAS adapter/loss audit | ModelIR | squash |
| E0-IR | ExecutionPlan/StateIR/ResultIR | ADR, R5 | squash |
| E0-CPU-op | CPU sparse operator | E0-IR | squash |
| E0-CPU-FGMRES | deterministic CPU oracle | CPU operator | squash |
| E1-context | HIP context/device identity | E0-IR | squash |
| E1-lineage | allocation lineage | E1-context | squash |
| E1-assembly | device assembly/resident CSR | lineage | squash |
| E1-free-space | free-space operator | resident CSR | squash |
| E1-Krylov | Krylov primitives | free-space | squash |
| E1-parity | hardware-gated parity | CPU oracle, Krylov | squash |
| E2-01..14 | 한 단계당 하나의 FGMRES lifecycle contract | 직전 E2 단계 | squash |
| E3-01..08 | 한 단계당 하나의 external trust contract | E2 parity, R6 where publishing | squash |
| G1-01..09 | 한 단계당 하나의 numerical closure contract | 직전 G1 단계, relevant E lane | squash |
| W-manifest | public asset/link contract | R3, R4 | squash |
| W-default | Workbench default-surface ADR/change | owner ADR | squash |
| V-* | generated evidence only | corresponding source merge | regular merge only if ancestry contract requires |

E2, E3 또는 G1의 여러 행을 한 PR로 합치지 않는다. 파일/라인 예산을 넘으면
contract를 더 작게 분할하며, generated evidence를 사용해 예산을 우회하지 않는다.

## 12. Verification matrix

| Lane | 필수 검증 | PASS로 볼 수 없는 것 |
| --- | --- | --- |
| R0 | JSON parse, enum completeness, family count 1,133, unclassified 0, links/path review | 분류 문서 존재만으로 integration readiness |
| R1 | metadata exact-set parity, targeted pytest/ruff, compileall, build, clean requirements install, `pip check`, package/sparse import | 이미 설치된 global SciPy로 수행한 import |
| R2 | same-path fail-before-write, atomic replacement, exception rollback, Windows semantics, compatibility | happy-path CLI 출력만 |
| R3/W | manifest schema/allowlist, forbidden pattern scan, link existence, artifact inventory, build, frontend contract, Playwright | local source 경로가 브라우저에서 우연히 열림 |
| R4 | workflow syntax/contract, Python-only/frontend-only/shared trigger cases | cancelled/queued workflow |
| R5 | byte-only vs semantic hash tests, propagation, v1/v2 compatibility/migration | 하나의 checksum 필드 재명명 |
| E0 | strict negative schemas, no-silent-loss audit, CPU dense/sparse/JVP/reaction/member-force oracle | schema PASS만 |
| E1/E2 | static/schema/adversarial/test-double + 별도 actual ROCm no-fallback parity, allocation/transfer/fence lineage | hardware 없는 local test-double |
| E3 | canonical encoding, signature, replay/rollback; separate reviewer/HSM/external receipts | synthetic key/local registry |
| G1 | central-difference JVP, accepted material-state replay, residual+increment at load 1.0, full mesh, HIP resident parity, fresh terminal receipt | 0.656 checkpoint, dry-run, partial mesh |
| V | clean checkout producer, source SHA/history, input checksum, generated-only diff, stale detection | source와 evidence 혼합 PR |

공통으로 `git diff --check`, changed-path Ruff, targeted pytest, package build를
실행한다. 실행하지 못한 test는 `NOT RUN`, 환경이 없는 hardware lane은
`SKIP/BLOCKED`로 보고한다.

## 13. Risk register

| 위험 | 영향 | 통제 |
| --- | --- | --- |
| Diverged stack를 merge/cherry-pick | main regression, provenance 혼합 | current-main 재구현, contract 단위 diff review |
| Source/evidence 혼합 | stale 또는 self-authored closure | 별도 branch/PR, protected path guard |
| Snapshot/doc drift | 과장된 readiness | canonical source SHA/status 병기, no-write checks |
| Metadata drift | clean install import failure | R1 exact-set contract + clean venv |
| CLI collision/non-atomic write | 결과 유실/혼합 | R2 fail-before-write/atomicity |
| Pages broad copy/hardcoded links | private/raw artifact 노출 | R3 allowlist/inventory/link check |
| Broad CI ownership | 장기 queue와 cancelled checks | R4 path split/contract tests |
| Hash semantics 혼합 | provenance 오판 | R5 source/canonical hash 분리 |
| HIP test-double promotion | production truth 오표시 | actual device identity/no-fallback gate 분리 |
| FGMRES lifecycle를 numerical closure로 오해 | false G1 claim | E2와 G1 DAG/receipts 분리 |
| Synthetic trust를 external trust로 오해 | false signed evidence claim | independent root/HSM/external ceremony 요구 |
| LFS clean-checkout 이상 | 재현성 실패 | 별도 pointer inventory/clean clone gate |
| 비구조 domain 재혼입 | product scope contamination | quarantine/extract, owner decisions |

## 14. STOP/GO criteria

다음 중 하나면 source PR 진행을 중지한다.

- base가 작업 시작 시점 최신 `origin/main`이 아님
- dirty/protected evidence와 변경 범위가 겹침
- source PR에 generated/protected evidence가 들어감
- 한 PR이 둘 이상의 public contract 또는 domain을 소유함
- 25 files/net 2,000 lines 예산 초과를 설명·분할하지 않음
- schema/API/ABI 변화에 migration note와 compatibility test가 없음
- 실패/미실행/hardware-unavailable test를 PASS로 표시함
- fallback, regularization, stale source 또는 host copy를 숨김
- owner/legal/human/external/hardware receipt를 코드로 생성해 closure 처리함
- claim boundary가 금지 표현으로 승격됨

R1의 GO 조건은 latest main 기반, 요구된 두 metadata/test source 변경과 R0 문서만,
generated evidence 및 Engine/G1/frontend/workflow diff 0, clean venv install/import,
targeted/unit/build 검증 성공, Draft PR 생성이다. GO는 merge 승인이 아니다.

## 15. 필요한 owner, hardware 및 external input

- structural-scope 86건과 release-surface 3건의 repository owner 결정
- root license/legal 승인 및 `CODEOWNERS`/`SECURITY`/`CONTRIBUTING` owner
- 실제 Windows clean replay owner/runner
- self-hosted ROCm/HIP runner와 exact device/driver/runtime identity
- external gfx1100 parity 실행 및 independent receipt
- customer shadow 3건, external benchmark 4건의 실제 입력/승인
- human new-user UX observation
- 30-run CI streak
- independent numerical V&V reviewer
- reviewer-root bootstrap 및 HSM/key ceremony
- release/deploy protected environment와 approved actor/ref 정책

이 입력이 없으면 관련 행은 BLOCKED로 남는다. 새로운 source/schema/test가 이를
대체하지 않는다.

## 16. First safe PR scope

Branch: `codex/repo-hygiene-runtime-dependency-parity-20260715`

Commit: `Align runtime dependency metadata`

Draft PR title: `Align required runtime dependencies across package metadata`

허용 변경은 다음뿐이다.

- `requirements.txt`: `scipy>=1.10`
- `tests/test_runtime_dependency_contract.py`: 세 metadata source의 required set parity
- 이 로드맵과 salvage map

Engine v2, G1, readiness producer, generated/protected evidence, frontend, workflow,
release, deployment, tag는 변경하지 않는다. PR은 Draft로만 열고 merge하지 않는다.
