# Engine v2 HIP FGMRES high-load model-case parity v2 / ResultIR v3

상태: v0.2.50 unpublished candidate, actual local `gfx1030` process-local
authority, contract-only, unsigned·비영속·non-promoting

## 목적

v0.2.48~v0.2.49는 원래 하중 크기의 rotated-axis `10 kN`, four/five-span
`100 kN` 케이스에서 componentwise FP64 CSR roundoff와 terminal
`L2/Linf/scaled-Linf` 차이를 caller tolerance 없이 검증했다. 그러나 기존
`hip_fgmres_model_case_parity.v1`은 고정 `numpy.allclose(rtol=1e-8,
atol=1e-12)` 정책을 포함하고 있고, completion ABI는 최종 `solution_x`, 최종
`true_residual`, opaque scalar `solve_record`만 내보낸다.

v0.2.50은 이 두 경계를 숨기지 않고 다음 두 additive wire를 추가한다.

1. `hip_fgmres_model_case_parity.v2`는 actual HIP authority와 정확히 하나의
   populated terminal restart row만 결속한다.
2. `hip_fgmres_result_ir.v3`는 retained ResultIRV2를 ready로 위장하거나 고정
   정책을 완화하지 않고, exported residual을 두 개의 componentwise roundoff
   receipt로 ResultIR physics에 연결한다.

## Restart-history ABI 증거 경계

현재 `solve_record`의 restart row는 다섯 scalar만 가진다.

```text
true_residual_l2
true_residual_linf
true_residual_scaled_linf
estimated_residual
solution_update_l2
```

중간 restart checkpoint의 solution vector와 true-residual vector는 export되지
않는다. 그러므로 각 중간 행의 scalar를 독립 sparse replay에 결속하는 일반
multi-restart history v2는 발행할 수 없다.

Model-case parity v2가 허용하는 범위는 다음과 같이 고정된다.

- populated restart row 수는 정확히 `1`
- 그 행은 최종 terminal row이고 1-based slot index와 최종 iteration/restart
  counter에 정확히 대응
- 세 true-residual scalar는 v0.2.49 vector-backed terminal metric receipt의
  `L2/Linf/scaled-Linf`와 exact alias
- `estimated_residual`과 `solution_update_l2`는 legacy fixed diagnostic 비교만 유지
- 두 diagnostic scalar의 roundoff-error model claim은 `false`
- 필요한 다음 ABI는
  `per_restart_checkpoint_solution_and_true_residual_vector_export_v2`

Receipt에는 아래 누락 증거를 명시적으로 기록한다.

- `intermediate_checkpoint_solution_vectors_not_exported`
- `intermediate_checkpoint_true_residual_vectors_not_exported`
- `estimated_residual_roundoff_model_not_available`
- `solution_update_roundoff_model_not_available`

두 개 이상의 populated row, terminal metric alias 불일치, 잘못된 slot/counter,
비정상 scalar, 누락 증거의 relabel은 모두 fail-closed한다. 기존 v1 schema hash와
고정 tolerance는 변경하지 않는다.

## Process-local model-case authority v2

`attest_hip_fgmres_model_case_parity_v2`는 retained live completion context를 통해
다음을 두 번 캡처하고 최종 발행 직전 동일성을 다시 확인한다.

- ModelIR/ExecutionPlanV2 및 CPU FGMRES reference
- terminal observation과 completion export receipt/payload
- HIP kernel/runtime/device identity와 실제 `gfx` architecture
- v0.2.49 terminal metric parity child receipt
- raw `solution_x`, `true_residual`, `solve_record` lineage

공개 receipt는 actual backend/device binding을 process-local 범위에서만 true로
기록한다. 직렬화된 receipt 자체, 복제된 dataclass 또는 coherent rehash는 이 권한을
보존하지 않는다. Exact factory issuance에는 non-recycled weak identity token이 필요하고,
context close 뒤에도 retained raw value와 발행 registry를 재생해 검증할 수 있다.

## ResultIR v2 동결과 additive v3

원래 고하중 residual은 stronger componentwise roundoff contract를 만족하면서도
ResultIRV2의 historical fixed residual-sign `allclose` gate를 통과하지 않을 수 있다.
v0.2.50은 이 실패를 tolerance 변경으로 덮지 않는다.

- 기존 `build_result_ir_v2`와 `validate_result_ir_v2_physics` 동작은 불변
- retained base ResultIRV2 wire는 structurally valid이지만
  `result_ir_ready=false`
- `retained_base_result_ir_ready=false`
- `result_ir_v2_fixed_residual_policy_relaxed=false`
- 기존 v2 test `29 passed`로 동결 경계를 재검증

ResultIR v3는 exported residual과 authoritative sparse physics 사이를 다음 두 단계로
검증한다.

```text
exported HIP true_residual
    -> independent math.fsum CSR replay
    -> ResultIR plan F - K*u
```

각 화살표는 v0.2.48의 componentwise FP64 CSR residual contract를 독립 발행하고
full replay한다. Reaction, member force, energy identity, full displacement/residual과
StateIR accepted→trial→committed lineage는 exported residual을 exact plan residual로
치환한 내부 fixed-physics ResultIRV2 witness로 재생한다. 이 witness는 공개 base v2를
ready로 승격하지 않는다.

ResultIR v3의 narrow `result_ir_v3_ready=true`는 정확히 이 process-local high-load
single-terminal-restart source와 sparse result recovery에만 적용된다. 추가 device,
D2H, solve, export, fallback은 각각 `0`이다.

## 검증

Contract와 회귀:

- model-case parity v2 focused: `4 passed in 9.44s`
- ResultIR v3 core receipt: `4 passed in 8.26s`
- ResultIR v3 public API/package 포함 전체 파일: `6 passed in 11.92s`
- 기존 ResultIR v2 불변 회귀: `32` cases, current cross-check에서 전부 통과
- ResultIR v2 + model-case v2 + ResultIR v3 + capability matrix:
  `56 passed in 45.09s`, wall `45.66s`, peak RSS `131,192 KiB`
- capability matrix: `14 passed in 0.32s`
- roundoff/model-case/ResultIR/all-converged/DiagnosticIR/capability adjacent:
  `222 passed in 739.43s (0:12:19)`, wall `740.15s`, peak RSS `143,452 KiB`
- strict Draft 2020-12 schema, canonical receipt, public API identity,
  Ruff/format/py_compile 통과
- hardware harness: `1 test collected`

적대 경로는 multirow/alias/slot/scalar 변조, v1 policy drift, 직접 생성한 ResultIR v3,
발행 전 payload 변조, base/witness/source splice를 거부한다.

Current-source single dirty non-release wheel은 `1,462,632` bytes/`287` members,
`sha256:5e55cfc00386d1c2a3ec6d2684a723e9eee661f904e10b01e469afba94c2971e`였다.
새 module 두 개와 schema 두 개의 archive/source byte equality를 확인하고, 소스 경로를
제거한 격리 설치에서 Engine/Assembly/Contracts/Elements public symbols
`966/780/93/10`과 공개 identity를 검증했다. 이는 단일 dirty smoke이며 reproducible 또는
authoritative release artifact 증거가 아니다.

## Actual local gfx1030 고하중 관찰

RX 6900 XT `gfx1030`에서 원래 하중 크기의 세 케이스를 current source로 실행했다.
모든 케이스에서 strict solution gate, recurrence D2H `0`, completion-export blocking D2H
exact `3`, failure `0`, fallback `0`, model-case v2와 ResultIR v3 post-close validation을
유지했다.

| case | case id | ResultIR v3 receipt hash | terminal 최대 ratio | legacy diagnostic 최대 ratio |
| --- | --- | --- | ---: | ---: |
| rotated-axis `-10,000 N` | `sha256:a77bbc613b883343656f89f20155c6736a4dafb5017963f1fc17a7961862a538` | `sha256:1131117f35c0931303c9d87f583c4977dd9e66a0387954b4c24b36ac8176ef7a` | `0.0023069006688603657` | update `4.040937665840211e-7` |
| four-span `100,000 N` | `sha256:bdd289c89050ffb13fbf7bff9c68084b2bb099866f8f97593ffd0b55fcba7c38` | `sha256:bc36f3bfcd99a2b7bd4b08f12155fba5c7fcc8ea1e70765a32a35e40d077f364` | `0.002952072072072049` | `0.0` |
| five-span `100,000 N` | `sha256:efd72111932880100fc3e5833e4cda5f13fe94e649260ebcb2063c7f1bb874e9` | `sha256:8164ccd54c65731f58947638af89bd0bbe6308ed1e268ae359523ba19bf215f2` | `0.00021165239437481313` | update `1.1514223855532976e-8` |

- required final-source gate: `1 passed in 430.66s (0:07:10)`
- wall time: `431.29s`
- process peak RSS: `430,796 KiB`
- 실행 전후 source aggregate:
  `sha256:9b902eb0b70102875b60efff4adbffc70420aeff26d7eb854988a080dea285f8`

이 값은 unsigned·비영속 local observation이다. 외부 runner의 서명된 hardware evidence나
release promotion evidence가 아니다.

## 아직 증명하지 않는 것

- 일반 multi-restart history v2
- 중간 checkpoint solution/true-residual vector export
- estimated-residual/solution-update roundoff error model
- retained base ResultIRV2가 fixed policy 아래 ready임
- 고하중 compatibility registry, family/aggregate authority
- standalone/persistent/signed provenance 또는 hostile same-process 보안
- external `gfx1100`, same artifact multiarchitecture parity
- broad iteration host-copy-zero, end-to-end `O(N)`, 성능/speedup
- nonlinear/dynamic/shell/solid/contact
- promotion eligibility 또는 commercial readiness

## 다음 순서

1. per-restart checkpoint solution/true-residual vector ABI와 두 diagnostic scalar의
   roundoff model을 추가해 일반 history v2를 설계한다.
2. v0.2.47 unit-load registry를 변경하지 않는 원래 고하중 compatibility
   registry/aggregate를 만든다.
3. 동일 final artifact를 external `gfx1100`과 local `gfx1030`에서 재생하고 signed
   provenance chain에 결속한다.
