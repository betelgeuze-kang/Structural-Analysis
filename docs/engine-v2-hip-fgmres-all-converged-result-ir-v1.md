# Engine v2 HIP FGMRES All-Converged ResultIR v1

- Milestone: v0.2.47 unpublished candidate
- Status: implemented contract and hardware harness; actual `gfx1030` gate pending
- Promotion: `contract_only`, non-promoting
- 기준일: 2026-07-16
- Authority: [Engine v2 master roadmap](structural-solver-engine-v2-master-roadmap.md)
- Fixed suite: [All-converged fixture registry v1](engine-v2-hip-fgmres-all-converged-fixture-registry-v1.md)

## 목적

이 vertical slice는 별도 all-converged registry의 exact live HIP model-case `10`개와
각 case에서 이미 발행된 ResultIRV2 bridge `10`개를 하나의 canonical aggregate로
결속한다. 목표 진실표는 다음과 같다.

```text
ready_result_ir_v2 = 10
solution_ready     = 10
not_issued         = 0
diagnostic_ir      = 0
committed_state    = 10
```

이는 v0.2.44/v0.2.45 termination-semantics registry의 역사적
`7 ResultIRV2 + 3 DiagnosticIRV1`을 수정하지 않는다. 신규 all-converged suite와 receipt는
별도 schema, package registry, live family authority 및 aggregate issuance를 사용한다.

## 세 단계 권한

```text
1. package all-converged registry
   -> ten unique CPU-converged ModelIR/ExecutionPlan fixtures

2. exact live HIP model-case results
   -> double-captured, registry-canonical all-converged family authority
   -> 10/10 live convergence and dual-tolerance lineage

3. exact already-issued ResultIRV2 bridges
   -> family/case/plan/provenance/terminal/export/device/state cross-binding
   -> canonical ten-bridge aggregate
   -> detached post-close value validation
```

Family receipt는 registry와 exact live case authority를 결속하지만
`result_ir_verified=false`다. Aggregate factory만 exact family authority와 각 case의
already-issued ResultIRV2 bridge를 entry, second, final capture에서 세 번 재검증한 뒤
`exact_ten_result_ir_v2_ready=true`를 발행한다.

Family와 aggregate receipt/manifest는 이 contract authority를 actual hardware evidence로
오인하지 않도록 `actual_hardware_execution_verified=false`와
`hardware_gate_completed=false`를 immutable claim으로 함께 발행한다. Required hardware
harness의 외부 PASS만으로 기존 receipt를 재해석하거나 두 필드를 true로 coherent rehash할
수 없으며, 해당 위조는 strict schema와 detached validator가 거부한다.

Public surface에는 private issuer나 weak-registry mint가 노출되지 않는다. Caller 입력
순서는 canonical registry 순서로 정렬되지만 missing, duplicate, foreign, unissued clone,
serially-identical cross-run splice, source identity race, coherent receipt/row rehash 및
issuance transplant는 fail-closed다.

## ResultIR 의미론

각 ResultIRV2 bridge는 기존 v0.2.43 계약을 그대로 사용한다.

- full displacement와 free solution
- full sparse `K*u-F` residual
- constrained reaction과 free exact `+0.0`
- local member force
- element/global/external/residual-work energy
- accepted -> evaluated trial -> committed StateIR lineage
- raw HIP `solution_x`/`true_residual` hash와 canonical ResultIR array hash 분리

Aggregate는 family observation과 bridge를 case ID, ModelIR/ExecutionPlan/CPU result,
terminal observation, completion export, device identity, architecture 및 state hash로
교차결속한다. Aggregate manifest는 descriptor-only이며 raw array 값을 JSON으로
직렬화하지 않는다.

## Exact aggregate totals

| 항목 | 값 |
| --- | ---: |
| Required / ready / solution-ready | `10 / 10 / 10` |
| Not-issued / DiagnosticIR | `0 / 0` |
| Unique ResultIR bridges / committed states | `10 / 10` |
| Package `G / E / F / nnz` | `168 / 18 / 103 / 2,304` |
| Result arrays | `60` (`6` per slot) |
| Result array bytes | `6,728` |
| Detached raw payload bytes | `1,648` |
| Upstream completion-export blocking D2H | `30 / 30 / 0` |
| Upstream completion-export allocated bytes | `4,288` |
| Aggregate additional device operations | `0` |
| Aggregate additional D2H / solve / export / fallback | `0 / 0 / 0 / 0` |

`4,288`은 completion-export가 실제 계측·할당한 byte extent 합계다. Logical-used
payload 합계 `4,216`을 이 필드로 대체하거나 actual transfer evidence로 재분류하지
않는다. 반대로 aggregate의 추가량 `0`은 composition factory direct-call surface에 대한
계약이며 process-wide ROCm/DMA 관찰 또는 broad host-copy-zero 증거가 아니다.

Registry validator는 aggregate/post-close validation 중에도 fixed suite와 CPU reference를
재생한다. 따라서 `registry_validation_cpu_reference_replay_zero_proven=false`가 canonical
claim이다.

## Lifetime과 provenance

Family issuance에는 exact live model-case identity가 필요하다. Aggregate issuance에는
그 exact family object와 ResultIR bridge identity가 필요하다. 발행된 aggregate는
detached family receipt와 exact bridges만 보유하며 HIP context close 뒤에도 sparse
physics, StateIR, array descriptor와 process-local issuance binding을 재검증할 수 있다.

그러나 JSON manifest 또는 detached receipt만으로 process-local provenance를 다시 얻을
수 없다. Standalone serialization, persistent external log, hostile same-process mutation
resistance 및 cryptographic signature는 이 계약에 포함되지 않는다.

## Contract 검증

현재 source의 구성은 다음과 같다.

- Fixed registry contract: `16 functions/27 collected cases` passed
- Live family authority contract: `9 functions/10 collected cases` passed
- Ten-bridge aggregate contract: `10 functions/15 collected cases` passed
- Public API/resource packaging and actual-wheel contract: `5` passed
- Combined current-source contract run: `57 passed in 264.00s (0:04:24)`
- Capability matrix: `11 passed in 0.31s`
- Current-source contract + capability 5-file cross-check:
  `68 passed in 262.53s (0:04:22)`
- Hardware harness: static full-replay-bound test와 actual gate, 합계 `2` tests collected

Contract tests는 canonical ordering과 전체 registry manifest `const`를 검증한다. Schema는
registry/case/registration/model-resource raw identity와 `expected`의 CPU·dense-oracle·package
plan/policy/descriptor hash `13`개를 exact `const`로 pin한다. Public/package test는 실제
wheel을 빌드한 뒤 fixture JSON `11`개와 schema `3`개의 archive path 및 source byte
동일성을 확인한다. 그 밖에 dual CPU tolerance, family/bridge identity, second/final capture
race, coherent rehash/transplant, aggregate module 전체 AST의 builder/solver/export/device
경로 부재, CPU registry replay를 허용하는 bounded validation, context close 뒤 validation을
포함한다. Family/aggregate issuance는 weak-key 회수 뒤 registry entry가 제거되고 새 token을
재사용하지 않는 것도 검증한다.

Replay 호출 수는 회귀로 상한을 고정한다. Family factory는 entry에서 full registry를
`1`회 replay하고 post-final raw-digest fast refresh를 `1`회 수행한다. Public family
result/receipt validator는 각각 fresh full replay `1`회다. Aggregate factory는 entry에서
full replay `1`회, exact live family/case/bridge recapture `3`회, second/final/post-final
raw-digest fast refresh `3`회를 수행하며 detached self-validator full replay는 없다. Public
aggregate result/receipt validator는 각각 fresh full replay `1`회다.

Required hardware 흐름의 exact full registry replay는 explicit initial `1` + family factory
`1` + aggregate entry `1` + post-close public aggregate `1` = `4`회다. 이는 `40` CPU solve와
`40` dense oracle에 해당하며, 최신 single-loader 약 `23s` 관찰을 단순 적용한 planning
cost는 약 `92s`다. 이 값은 성능 보증이 아니다. Fast raw refresh는 family `1` + aggregate
`3` = `4`회다.

현재 root host에는 `/dev/kfd`가 존재하고 `_local_architectures=('gfx1030',)`, probe ready,
backend `hip_native`, fallback false다. 다만 required all-converged actual gate는 아직
완료하지 않아 current-source actual local `gfx1030` 10/10과 peak RSS는 pending이다.
별도 restricted namespace에는 `/dev/kfd`가 없었고, non-required mode는 static bound test가
통과한 뒤 actual gate가 skip되어 `1 passed, 1 skipped in 1.74s`, required mode는 static
test가 통과한 뒤 actual gate가 `No real gfx agent was detected.`로 fail-closed하여
`1 passed, 1 failed in 1.76s`였다. 이는 현재 root-host probe를 반박하거나 durable
hardware observation을 생성하지 않는다.
v0.2.45의 과거 `5757.94s`와 current-source `7820.35s` actual run은 termination
registry용이며 이 신규 aggregate의 actual evidence로 재사용하지 않는다.

실제 wheel의 JSON `11`개와 schema `3`개 exact path/byte 검증은 package completeness
smoke일 뿐 clean source/release identity, actual HIP, signature 또는 promotion 증거가
아니다.

별도 final non-release wheel smoke는 동결된 `390`개 input tree 전후
`sha256:4bd5ccec…4358` 동일성을 확인하고 `1,401,376` bytes,
`sha256:8beb53e159c25decaa5c105fd771163ef15a968a3381c44550b2c0dfbaa92a3e` wheel의
Engine/Assembly/Contracts/Elements public symbols `886/730/63/10`, 관련 schema `5`, fixture
JSON `11`, registry `10`-slot fresh CPU replay를 격리 설치에서 통과했다. 이는 dirty
non-release package smoke이며 clean release identity나 hardware evidence가 아니다.

## 현재 true와 pending

Contract/test-double source에서 true:

- 별도 package registry의 CPU convergence·dual tolerance `10/10`
- exact live authority 및 exact bridge identity를 요구하는 family/aggregate contract
- canonical `10 ready + 0 not-issued + 0 diagnostic` aggregate 의미론
- `G=168,E=18,F=103,nnz=2304`, arrays `60/6728`, detached `1648`
- upstream D2H contract `30/30/0`, allocated `4288` bytes
- aggregate direct additional device/D2H/solve/export/fallback `0`
- post-close process-local detached value validation
- family/aggregate manifest의 `actual_hardware_execution_verified=false` 및
  `hardware_gate_completed=false`

Pending 또는 false:

- current-source actual local `gfx1030` 10/10 ResultIR hardware 통과
- actual peak RSS
- external `gfx1100`와 multiarchitecture/same-process two-ISA 결과
- GPU-native reaction/member-force/energy recovery 자체
- process-wide/broad iteration host-copy-zero
- standalone, persistent, signed provenance 및 promotion eligibility
- GPU recovery, crash/reset/cross-process abandoned owner recovery
- end-to-end O(N), performance 또는 speedup
- nonlinear/dynamic/shell/solid/contact
- commercial readiness

## 실행 gate

```bash
# 계약 및 public/package 경계
PYTHONPATH=src python3 -m pytest -q \
  tests/test_engine_v2_hip_fgmres_all_converged_fixture_registry_v1.py \
  tests/test_engine_v2_hip_fgmres_all_converged_model_family_v1.py \
  tests/test_engine_v2_hip_fgmres_all_converged_result_ir_v1.py \
  tests/test_engine_v2_all_converged_result_ir_v1_public_api.py

# 실제 gfx1030 required gate: static replay bound 통과만으로 actual 완료 처리하지 않음
ENGINE_V2_REQUIRE_HIP_FGMRES_ALL_CONVERGED_RESULT_IR_V1_HARDWARE=1 \
PYTHONPATH=src python3 -m pytest -q \
  tests/test_engine_v2_hip_fgmres_all_converged_result_ir_v1_hardware.py
```

## 다음 단계

1. Actual `gfx1030`에서 per-case 및 aggregate peak RSS를 계측한다.
2. 동일 current source/package resources로 required hardware gate를 실행해 actual
   `10/10` family, bridge, aggregate 및 post-close validation을 닫는다.
3. Reviewer-root bootstrap/HSM lifecycle 뒤 external `gfx1100`, 동일 final artifact local
   `gfx1030`, durable monotonic ledger 및 signed evidence를 순서대로 검증한다.
4. Broad iteration host-copy-zero와 GPU result recovery를 별도 authoritative gate로 닫은
   뒤에만 O(N), speedup 또는 commercial/promotion claim을 검토한다.
