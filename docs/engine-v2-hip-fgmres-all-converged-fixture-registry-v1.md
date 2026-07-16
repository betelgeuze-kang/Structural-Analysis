# Engine v2 HIP FGMRES All-Converged Fixture Registry v1

- Milestone: v0.2.47 unpublished candidate
- Status: implemented, `contract_only`, actual local `gfx1030` gate observed,
  non-promoting
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

All-converged suite는 termination source model `7`개의 raw bytes를 그대로 보존한다.
Cancellation-sensitive rotated-axis와 four-span case는 원본 기하·재료·section·support를
유지하되 각각 FY/FX `1 N` 단위하중으로 정규화한 명시적 derivative이고, five-span은
처음부터 별도로 생성한 `1 N` normalized model이다. 이 세 case는 기존 v1의 고정
`atol + rtol*|CPU|` residual parity 규칙을 변경하거나 tolerance를 완화하지 않는다.
Generator
`scripts/regenerate_engine_v2_all_converged_registry.py`가 이 세 slot만 다시 컴파일해
registry와 strict schema hash pin을 재생하며 나머지 slot row는 그대로 보존한다.

## 고정 suite

| 순서 | Slot | CPU iteration | 분류 |
| ---: | --- | ---: | --- |
| 1 | `solution_frame_single_axial` | 1 | nontrivial solution |
| 2 | `solution_frame_single_weak_axis_bending` | 2 | nontrivial solution |
| 3 | `solution_frame_single_strong_axis_bending` | 2 | nontrivial solution |
| 4 | `solution_frame_single_torsion` | 1 | nontrivial solution |
| 5 | `solution_frame_single_rotated_axis_bending` | 6 | normalized-unit-load nontrivial solution |
| 6 | `solution_frame_serial_two_span_axial` | 2 | nontrivial solution |
| 7 | `solution_truss_single_axial` | 1 | nontrivial solution |
| 8 | `solution_frame_zero_free_rhs_edge` | 0 | explicit zero-free-RHS edge |
| 9 | `solution_frame_serial_four_span_axial` | 4 | normalized-unit-load nontrivial solution |
| 10 | `solution_frame_serial_five_span_axial` | 5 | normalized-unit-load nontrivial solution |

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
| Registry raw bytes SHA-256 | `sha256:e3414a08530703a9cc4405393157c9c88f6a721b2dbf5717e77c6a5dee7f31f1` |
| Registry canonical content hash | `sha256:85611ec01af14b375be09f91ee67e9eb2ee89734f110ff9899239465d5793a19` |
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
- Combined contract scope: `57` cases passed within the 5-file cross-check below
- Capability matrix: `11 passed in 0.31s`
- Current-source contract + capability 5-file cross-check:
  `68 passed in 259.34s (0:04:19)`
- Hardware harness: static full-replay-bound test와 actual gate, 합계 `2` tests collected
- Current-source required local `gfx1030` actual gate는 RX 6900 XT에서 CPU fallback 없이
  `1 passed in 1087.52s (0:18:07)`로 통과했다. Exact live case/ResultIR bridge `10/10`,
  family, aggregate와 context close 뒤 detached validation을 한 프로세스에서 확인했다.
  Baseline/각 case/family/aggregate/post-close RSS checkpoint를 계측했고 process peak는
  `450,868 KiB`(약 `440.3 MiB`), post-close current RSS는 `433,188 KiB`였다.
- 실행 전후 Engine source/schema/fixture aggregate
  `sha256:41bf10b8e4fb506b5829d386ff3ad24a7ece76bcfbd4be4865e2fa8dedcaac30`,
  hardware harness
  `sha256:4d43b262b57696de8e04b591fa79adad0dc06815114176319d45e25f03d67681`,
  shared live harness
  `sha256:3b0acb3ab1af894f5ef099c227614b54983f51857c1dce08e0def9977df00bde`가
  동일했다.
- 첫 실제 run은 rotated-axis, 두 번째 run은 four-span의 수렴 후 near-zero raw residual
  absolute parity에서 fail-closed했다. CPU/HIP scaled residual과 solution은 통과했으나
  cancellation residual의 계산 순서 차이가 v1 고정 absolute floor를 넘었다. 세
  cancellation-sensitive fixture를 unit load로 정규화한 뒤 각 case를 별도로 strict
  parity/ResultIR-ready 검증하고 최종 10-slot run을 다시 통과했다. 이 registry 자체는
  일반적인 scale-aware residual 계약을 증명하지 않는다. 별도 downstream v0.2.48은
  원래 고하중 세 case의 componentwise roundoff/backward-error vector gate를 actual
  `gfx1030`에서 `1 passed in 218.17s`로 통과했지만 이 v0.2.47 ResultIR authority에
  소급하지 않는다. Downstream v0.2.49 terminal norm record gate도 같은 세 고하중
  case에서 final-source `1 passed in 226.25s`로 통과했지만 이 registry의 ResultIR/aggregate
  authority에는 소급하지 않는다.
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
- Current-source final non-release wheel smoke는 `1,401,602` bytes,
  `sha256:d9deea5512465f5fea353fffa4cab036eb03dff91fbbedf78c8a98bc560efc00` wheel의
  Engine/Assembly/Contracts/Elements public symbols `886/730/63/10`, 관련 schema `5`,
  fixture JSON `11`, registry `10`-slot fresh CPU replay를 소스 경로를 제거한 설치에서
  통과했다. 현재 런타임 의존성을 사용한 단일 dirty non-release package smoke이며
  reproducible build 또는 release identity가 아니다.
- 같은 source의 연속 wheel 두 개는 모두 `1,401,602` bytes와 `264` members였고 member
  content diff는 `0`이었지만 `dist-info` 5개 timestamp가 달라 archive hash가
  `sha256:f704a687e0ca13233c2fb379a9b71714888c6e0c192b120f3fa2cae82fa08838`와
  `sha256:18bcb7f7f405ceb5be75474e0926bcf906bc35ad274d9946faa7d09ba4da0ba0`로
  달랐다. 따라서 현재 reproducible wheel build는 명시적으로 false다.

과거 v0.2.45 통합 `gfx1030` `5757.94s`와 current-source `7820.35s` 결과는 다른
termination registry의 7-result/3-diagnostic lineage이므로 이 신규 registry의 actual
HIP 또는 10/10 ResultIR 증거로 재사용하지 않는다.

## Claim 경계

현재 true인 것은 package-owned fixed suite, 10개 고유 ModelIR/plan, CPU convergence 및
두 tolerance gate뿐이다. 다음은 이 registry만으로 증명하지 않는다.

- external `gfx1100`, multiarchitecture 또는 same-process two-ISA parity
- standalone/persistent/signed provenance와 promotion eligibility
- broad/process-wide iteration host-copy-zero
- GPU reaction/member-force/energy recovery
- end-to-end O(N), 성능 또는 speedup
- 이 registry 자체의 일반 load scale roundoff-aware ResultIR/terminal metric parity
- nonlinear/dynamic/shell/solid/contact
- commercial readiness

## 다음 단계

1. v0.2.49 additive terminal `L2/Linf/scaled Linf` v2 이후 restart-history metric과
   고하중 ResultIR bridge/compatibility registry를 결속한다.
2. External `gfx1100` 및 동일 final artifact의 local `gfx1030` 재실행, durable/signed
   provenance, broad host-copy-zero를 순서대로 추가한다.
