# Engine v2 HIP FGMRES terminal-outcome observation v1

- 상태: Phase 0 implemented, `contract_only`/non-promoting
- schema version: `structural-analysis-hip-fgmres-terminal-outcome-observation.v1`
- capability profile: `phase0_completion_export_bound_terminal_record_observer`
- evidence scope: `context_bound_terminal_record_semantics_observed_non_promoting`
- 입력: [completion-only export v1](engine-v2-hip-fgmres-completion-export-v1.md)의 exact final result와 process-local export context
- ABI: [HIP FGMRES full recurrence ABI v2](engine-v2-hip-fgmres-recurrence-abi-v2.md)

## 범위

이 observer는 completion exporter가 내보낸 immutable `solution_x`, `true_residual`, `solve_record`를 host에서 해석한다. Exporter 자체의 receipt, payload, hash와 outcome-free claim은 변경하지 않고 별도 observation receipt를 발행한다.

권위 구현은 [terminal observer source](../src/structural_analysis/engine_v2/assembly_backend/fgmres_terminal_outcome_observation_v1.py), 직렬화 계약은 [Draft 2020-12 schema](../src/structural_analysis/schemas/hip_fgmres_terminal_outcome_observation_v1.schema.json)에 있다.

## 사용 계약

```python
export_result = export_context.export_completion_buffers()

observation = observe_hip_fgmres_terminal_outcome_v1(
    export_result,
    expected_export_context=export_context,
)

validate_hip_fgmres_terminal_outcome_observation_result_v1(observation)
validate_hip_fgmres_terminal_outcome_observation_receipt_v1(
    observation.receipt,
    expected_export_result=export_result,
    expected_export_context=export_context,
)

manifest = observation.to_manifest()
```

Observer 생성과 public receipt 검증에는 exact final export result 및 동일 process-local context가 필요하다. 직렬화된 manifest에는 Python object identity가 포함되지 않으며 `process_local_result_identity_serialized=false`로 고정된다. 따라서 manifest만으로 provenance authenticity를 재인증할 수 없다. 장기 보관·외부 전달은 향후 signed chain의 범위다.

`ReceiptV1.to_dict()`는 직렬화 구조·schema·hash·source-independent 의미론을 검증한다. `validate_*_receipt_v1()`은 그 위에 exact source result와 context seal replay를 추가한다.

## Final-publication seal

Completion exporter는 public raw receipt를 변경하지 않는 private seal에 다음을 결속한다.

- exact final result, receipt 및 세 detached `bytes` identity
- receipt/payload/세 buffer hash
- `M`, `I`, `R`, stagnation limit
- absolute/relative/authoritative tolerance, stagnation tolerance, divergence factor

Seal은 publication 직전에 parent global authority를 다시 조회한 값으로 만들고 단일 tuple store로 publish한다. 따라서 local policy TOCTOU와 seal/snapshot 사이 interruption을 fail-closed 또는 monotonic retry로 처리한다. Intermediate `_publication`, 다른 context의 result, rehashed mutation 및 final result identity 교체는 observer 입력이 될 수 없다.

## Decode 및 의미론

Observer는 native dtype view에 의존하지 않고 `<i`와 `<d`로 little-endian ABI를 명시적으로 decode한다.

```text
header       192 bytes = 16*i32 + 16*f64
restart row   72 bytes = 8*i32 + 5*f64
record       192 + 72R bytes
```

검증 범위는 다음과 같다.

- `active == 0`, known terminal status와 exact termination-code 조합
- recurrence ABI v2, current solve-record/control/kernel ABI hash
- known device error mask, exact ordered error names, termination code별 kernel-reachable error-mask 조합
- `M`, `I`, `R`, effective iteration/restart/Arnoldi/operator/preconditioner counter 관계
- solver L2 gate와 authoritative scaled-Linf gate
- contiguous, atomically committed restart-row prefix와 unused all-zero suffix
- exact restart index/start/end/step, termination hint, gate/terminal flags
- convergence/divergence/stagnation/max-iteration priority와 stagnation suffix history
- nonfailure header metric, final restart row 및 exported `true_residual`의 deterministic tree L2/Linf/scaled 값 일치

현재 ABI의 17개 terminal termination code를 모두 처리한다. `cancelled` 상태는 device ABI에 없으므로 observer가 새로 만들지 않는다.

### Numerical failure

`numerical_failure`에서는 header numerical metrics와 solution/residual norm을 권위 값으로 사용하지 않는다.

- `record_metrics_authoritative=false`
- `metrics=null`
- observed solution/residual norm과 record-match 값은 `null`
- payload의 component finiteness boolean만 기록
- 이미 완전히 commit된 nonterminal `restart_completed` row prefix만 보존
- partial current row, terminal flag가 섞인 과거 row, impossible gate/stagnation/counter history는 거부
- committed 과거 row가 있으면 stable baseline·scaled residual·gate·plateau·latest tiny-update predicate를 raw decode에서 재계산

따라서 failure payload가 finite이지만 norm 계산에서 overflow할 수 있어도 observer가 불필요한 norm을 실행하지 않는다.
과거 row의 latest tiny-update는 header의 latest `solution_scale_l2`로 재계산하지만, 더 이전 row의 각 `x_scale` 값은 ABI에 보존되지 않으므로 개별 tiny predicate를 수치적으로 다시 증명하지 않는다. 그 부분은 committed flag suffix와 stagnation count 관계만 검증한다.

### Solution payload

Nonfailure에서도 `solution_x` component finiteness만 확인하고 solution norm은 계산·발행하지 않는다. 이 observer는 equilibrium replay나 solution-ready contract가 아니기 때문이다. `true_residual` norm 일치는 exported bytes와 solve record의 내부 일관성만 증명하며 `r=b-Ax`를 다시 계산했다는 뜻이 아니다.

## 별도 receipt와 telemetry

정상 observation receipt는 raw exporter와 독립된 hash domain을 사용한다. `outcome_hash`는 해석된 outcome에, `receipt_hash`는 bindings/dimensions/policy/outcome/telemetry/claims 전체에 결속된다.

Telemetry의 `completion_export_source_result_count=1`, `solve_record_payload_count=1`, header field `32`, restart slot `R`은 중복 validator 호출 횟수가 아니라 receipt가 설명하는 unique logical source/payload/field 수다. Observer 범위에서 다음 operation은 모두 0이다.

```text
additional D2H / H2D                    0 / 0
device allocation / allocation borrow  0 / 0
kernel launch / explicit stream sync    0 / 0
fallback                                0
```

Host work는 이미 export된 `F` 길이 residual과 `R` restart slot을 한정적으로 검사하므로 `O(F+R)`이다. 이는 전체 solver의 일반 `N`-DOF O(N) 복잡도 증거가 아니다.

## Claim boundary

Exact process-local provenance와 semantic replay가 성공했을 때만 다음이 true다.

- raw completion export result가 결속되고 변경되지 않음
- solve-record terminal semantics와 invariants가 해석됨
- actual terminal outcome이 host에서 관찰됨
- 해당 exact device record의 terminal status가 authoritative함
- observer 자체의 추가 device operation이 없음

다음은 계속 false다.

- authoritative completion/solution receipt
- CPU/HIP numerical parity
- solution/equilibrium/ResultIR readiness
- residual equation replay
- model-family 또는 multi-architecture parity
- iteration host-copy-zero
- 일반 O(N), kernel/solver speedup 또는 performance claim
- commercial readiness와 promotion eligibility

## 검증

- Unit/adversarial gate: 17개 termination code, failure code별 32개 reachable error-mask 조합, schema/hash/exact scalar type, signed zero·NaN·Inf·unknown/mismatched bit·partial row·counter/history·rehashed semantic forgery, policy/final-publication seal mutation과 provenance mismatch
- Actual HIP gate: gfx1030 later-column convergence와 active `FINAL_GUARD` max-iteration 두 경로
- Hardware observer 구간: device allocation/H2D/D2H/kernel/sync 0
- Upstream raw export: blocking D2H 정확히 3회이며 exporter/global receipt 불변
- CPU oracle: observation receipt 발행 이후 test-only 비교이며 product parity claim이 아님
- Package gate: wheel `918843` bytes (`sha256:80c8861d8ddc0d880afc88c245ee077e33ba764f64f1da432eab09aed4822b5c`), sdist `2595050` bytes (`sha256:8965d91fa04ffcc5bc3720d941653f45e143239a813d89cafa81f09d56a793e8`); wheel 격리 설치에서 public symbol 18개 identity, `29927`-byte schema와 `214715`-byte HIP source resource를 확인

## 다음 단계

다음 우선순위는 model-family·multi-architecture CPU/HIP full recurrence parity다. 그 다음 iteration host-copy-zero를 별도 계측으로 닫고, 이후에만 authoritative ResultIR 및 상위 solver 결과 통합을 진행한다.
