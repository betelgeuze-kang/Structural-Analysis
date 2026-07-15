# Engine v2 HIP FGMRES All-Converged Fixture Registry v1

- Milestone: v0.2.47 unpublished candidate
- Status: implemented, `contract_only`, non-promoting
- 기준일: 2026-07-16
- Authority: [Engine v2 master roadmap](structural-solver-engine-v2-master-roadmap.md)
- Result vertical slice: [HIP FGMRES all-converged ResultIR v1](engine-v2-hip-fgmres-all-converged-result-ir-v1.md)

## 목적

이 registry는 기존 termination-semantics fixed registry를 변경하지 않고, 실제
해가 필요한 `9`개 case와 명시적 zero-free-RHS edge `1`개를 합친 별도
all-converged `10`-slot suite를 package resource로 고정한다. 모든 slot은 서로 다른
ModelIR, ModelIR content hash, ExecutionPlanV2 hash 및 case fingerprint를 가지며,
CPU reference의 solver tolerance와 authoritative-plan residual tolerance를 모두
통과해야 한다.

이 계약은 **fixture와 CPU replay의 권한**만 제공한다. Registry receipt 자체의
`actual_hip_execution_verified`, `result_ir_verified`, `signed_evidence`,
`promotion_eligible`은 모두 `false`다. 실제 HIP family 및 ResultIR 권한은 별도 live
factory와 hardware gate에서만 발행할 수 있다.

후속 family/aggregate contract receipt도 contract authority와 실제 gate 완료를 분리해
`actual_hardware_execution_verified=false`, `hardware_gate_completed=false`를 immutable
claim으로 직렬화한다. 이 두 값은 detached manifest의 coherent rehash로 승격할 수 없다.

## 기존 종료 의미론과의 분리

기존 `fgmres_family_v2/registry.v1.json`은 intentional `max_iterations` 3건을 포함하는
종료 의미론 fixture다. v0.2.44의 `7 ResultIRV2 ready + 3 not-issued`와 v0.2.45의
`7 ResultIRV2 + 3 DiagnosticIRV1` 역사적 사실은 그대로 유지한다.

새 registry는 다음 별도 resource root를 사용한다.

```text
structural_analysis.engine_v2.assembly_backend.fixtures.fgmres_all_converged_v1/
  registry.v1.json
  solution_frame_single_axial.model.json
  solution_frame_single_weak_axis_bending.model.json
  solution_frame_single_strong_axis_bending.model.json
  solution_frame_single_torsion.model.json
  solution_frame_single_rotated_axis_bending.model.json
  solution_frame_serial_two_span_axial.model.json
  solution_truss_single_axial.model.json
  solution_frame_zero_free_rhs_edge.model.json
  solution_frame_serial_four_span_axial.model.json
  solution_frame_serial_five_span_axial.model.json
```

기존 termination registry raw bytes hash는
`sha256:bc12d11a15d23f2768e4c27e5f8449f88d26453f9579ebb741861a3176eae2fa`로
동결되어 있고, 신규 테스트가 이 불변성을 함께 확인한다.

## 고정 suite

| 순서 | Slot | CPU iteration | 분류 |
| ---: | --- | ---: | --- |
| 1 | `solution_frame_single_axial` | 1 | nontrivial solution |
| 2 | `solution_frame_single_weak_axis_bending` | 2 | nontrivial solution |
| 3 | `solution_frame_single_strong_axis_bending` | 2 | nontrivial solution |
| 4 | `solution_frame_single_torsion` | 1 | nontrivial solution |
| 5 | `solution_frame_single_rotated_axis_bending` | 6 | nontrivial solution |
| 6 | `solution_frame_serial_two_span_axial` | 2 | nontrivial solution |
| 7 | `solution_truss_single_axial` | 1 | nontrivial solution |
| 8 | `solution_frame_zero_free_rhs_edge` | 0 | explicit zero-free-RHS edge |
| 9 | `solution_frame_serial_four_span_axial` | 4 | nontrivial solution |
| 10 | `solution_frame_serial_five_span_axial` | 5 | nontrivial solution |

모든 slot은 CPU FGMRES `relative_tolerance=1.0e-12`와 ExecutionPlanV2
`residual_tolerance=1.0e-10`을 사용한다. Registry replay는 각 case에 대해 다음을
동시에 확인한다.

- CPU terminal status `converged`
- solver tolerance passed `10/10`
- authoritative-plan tolerance passed `10/10`
- deterministic dense oracle와 solution parity
- physical semantic profile, load, support, coordinates, connectivity 및 section/material
- 고유 ModelIR raw bytes/content hash, ExecutionPlanV2 hash 및 registration hash
- canonical required-slot 순서

Zero-RHS edge는 `converged_initial_true_residual`, iteration `0`, 빈 history를 요구한다.
일반 case의 반복 회피용 허술한 tolerance 또는 expected-status override는 허용하지 않는다.

## Hash 권한

| 항목 | 고정값 |
| --- | --- |
| Registry raw bytes SHA-256 | `sha256:f1e7342a846db16af0a88bd2f410b4685206b17cee850b96157c5be40730a28a` |
| Registry canonical content hash | `sha256:dfc836a87b604a8aff066a4d9b6746311184477d8b0db4788479fb1c9d782aff` |
| Registered slots | `10` |
| Unique model raw hashes | `10` |
| Unique ModelIR content hashes | `10` |
| Unique ExecutionPlanV2 hashes | `10` |
| Nontrivial / zero-free-RHS | `9 / 1` |

Raw resource bytes를 parse 전에 검증하고, canonical content hash는 `registry_hash`
필드를 제외한 strict JSON object에 대해 계산한다. Duplicate key, BOM, nonfinite JSON,
unknown property, slot reorder, resource mutation, duplicate registration/model/plan hash는
모두 fail-closed다. Public loader는 인자를 받지 않아 caller가 파일 경로나 policy를
override할 수 없다.

Schema는 전체 registry manifest를 exact `const`로 고정한다. 또한 각 slot의 identity와
model resource/raw bytes, case fingerprint, slot registration hash 및 `expected` 아래의
CPU result/history/solution/residual, dense-oracle solution/residual, ModelIR·free-space·FGMRES·
recurrence·ExecutionPlan·policy·descriptor hash `13`개를 개별 exact `const`로 확인한다.
따라서 registry hash만 다시 계산한 일관된 위조도 schema 단계에서 허용하지 않는다.

## 권한 흐름

```text
fixed package JSON resources
  -> strict schema/raw hash/content hash
  -> ModelIR v2 + ExecutionPlanV2 replay
  -> deterministic dense oracle + CPU FGMRES dual tolerance
  -> detached registry result (CPU fixture authority only)
  -> exact ten live HIP model-case authorities
  -> process-local all-converged family authority
  -> ten ResultIRV2 bridges and aggregate
```

Registry validation은 의도적으로 deterministic CPU reference를 재생하므로
`registry_validation_cpu_reference_replay_zero`는 **false**다. 이 replay를 HIP solve나
fallback으로 세지 않지만, CPU replay가 없다고 주장해서도 안 된다.

## 검증 상태

- Registry contract: `16 functions/27 collected cases` passed
- Family contract: `9 functions/10 collected cases` passed
- ResultIR aggregate contract: `10 functions/15 collected cases` passed
- Public/package and actual-wheel contract: `5` passed
- Combined current-source contract run: `57 passed in 264.00s (0:04:24)`
- Capability matrix: `11 passed in 0.31s`
- Current-source contract + capability 5-file cross-check:
  `68 passed in 262.53s (0:04:22)`
- Hardware harness: static full-replay-bound test와 actual gate, 합계 `2` tests collected
- 현재 root host에는 `/dev/kfd`가 존재하고 `_local_architectures=('gfx1030',)`, probe
  ready, backend `hip_native`, fallback false다. 다만 required all-converged actual gate는
  아직 완료하지 않았으므로 actual local `gfx1030` 10/10과 peak RSS는 pending이다.
- 별도 restricted namespace에는 `/dev/kfd`가 없었다. Non-required mode는 static test가
  통과하고 actual gate가 skip되어 `1 passed, 1 skipped in 1.74s`였고, required mode는
  static test가
  통과한 뒤 actual gate가 `No real gfx agent was detected.`로 fail-closed하여
  `1 passed, 1 failed in 1.76s`였다. 이는 현재 root-host probe를 반박하거나 durable
  hardware observation을 생성하지 않는다.
- Public/package test는 현재 source에서 실제 wheel을 빌드한 뒤 archive 안의 fixed fixture
  JSON `11`개와 schema `3`개의 exact package path 및 byte를 source resource와 대조한다.
  이는 package completeness smoke이며 clean release identity, actual HIP, signature 또는
  promotion 증거가 아니다.
- 별도 final non-release wheel smoke는 동결된 `390`개 input tree 전후
  `sha256:4bd5ccec…4358` 동일성을 확인하고 `1,401,376` bytes,
  `sha256:8beb53e159c25decaa5c105fd771163ef15a968a3381c44550b2c0dfbaa92a3e` wheel의
  Engine/Assembly/Contracts/Elements public symbols `886/730/63/10`, 관련 schema `5`,
  fixture JSON `11`, registry `10`-slot fresh CPU replay를 격리 설치에서 통과했다. 이 또한
  dirty non-release package smoke이며 release identity가 아니다.

과거 v0.2.45 통합 `gfx1030` `5757.94s`와 current-source `7820.35s` 결과는 다른
termination registry의 7-result/3-diagnostic lineage이므로 이 신규 registry의 actual
HIP 또는 10/10 ResultIR 증거로 재사용하지 않는다.

## Claim 경계

현재 true인 것은 package-owned fixed suite, 10개 고유 ModelIR/plan, CPU convergence 및
두 tolerance gate뿐이다. 다음은 이 registry만으로 증명하지 않는다.

- actual local `gfx1030` 실행 또는 ResultIR 발행
- external `gfx1100`, multiarchitecture 또는 same-process two-ISA parity
- standalone/persistent/signed provenance와 promotion eligibility
- broad/process-wide iteration host-copy-zero
- GPU reaction/member-force/energy recovery
- peak RSS, end-to-end O(N), 성능 또는 speedup
- nonlinear/dynamic/shell/solid/contact
- commercial readiness

## 다음 단계

1. Actual `gfx1030` 환경에서 peak RSS를 별도 측정해 현재 ordered gate를 닫는다.
2. 같은 current source와 fixed resource로 required all-converged hardware harness를 실행해
   `10/10` live family와 ResultIR aggregate를 검증한다.
3. External `gfx1100` 및 동일 final artifact의 local `gfx1030` 재실행, durable/signed
   provenance, broad host-copy-zero를 순서대로 추가한다.
