# Engine v2 HIP FGMRES 고하중 registry / ResultIR aggregate v1

- Milestone: v0.2.51 unpublished candidate
- 기준일: 2026-07-17
- 상태: implemented, contract-only, unsigned, non-persistent, non-promoting
- 대상: 원래 하중 rotated-axis `10 kN`, four-span/five-span `100 kN` 선형 frame 3건

## 1. 목적

v0.2.50은 실제 로컬 `gfx1030`에서 세 원래 하중 케이스의 model-case parity v2와 ResultIR v3를 통과했지만, 모델 생성이 hardware test helper 안에 남아 있었고 세 결과를 하나의 package-owned registry 및 aggregate로 묶지 않았다. v0.2.51은 이 공백을 다음 두 계약으로 닫는다.

1. 고하중 모델 3건을 package resource로 고정하고 역사적 v0.2.47 unit-load registry와의 load-only 호환성을 전수 재생한다.
2. 이미 발행된 정확한 ResultIR v3 세 개를 registry 순서로 canonicalize하고 case/plan/CPU/terminal/export/device/state/roundoff 체인을 하나의 aggregate receipt로 교차 결속한다.

이 변경은 v0.2.47 registry의 모델이나 raw bytes를 수정하지 않으며 v0.2.50 ResultIR v3의 단일 케이스 의미론도 완화하지 않는다.

## 2. package-owned 고하중 registry

고정 identity는 다음과 같다.

- registry raw bytes: `sha256:7411b02b72500b7448ed97dd3470d27e8fb129a7d98ee600b2ff06374a1b113d`
- registry canonical content: `sha256:72ea556471edb72a2262f870e76d4fc423e9d665da82f6d8e4d03dd6ae953f9e`
- full-const schema raw bytes: `sha256:5883c16075f8ebabdc7e8a6dfdb2b300e3c89973cc14ea6e955bbd1d16f9ac75`
- parent v0.2.47 registry raw bytes: `sha256:e3414a08530703a9cc4405393157c9c88f6a721b2dbf5717e77c6a5dee7f31f1`
- parent canonical content: `sha256:85611ec01af14b375be09f91ee67e9eb2ee89734f110ff9899239465d5793a19`
- parent schema raw bytes: `sha256:cfe3a37ab6d9db1adbe5d26a6b1a0549eae8591d0adc5a00fbc5865d07dc00ab`

| slot | parent | load | scale | G | E | F | nnz | CPU iterations |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `high_load_frame_single_rotated_axis_bending_10kn` | `solution_frame_single_rotated_axis_bending` | `FY=-10,000 N` | `10,000` | 12 | 1 | 6 | 144 | 6 |
| `high_load_frame_serial_four_span_axial_100kn` | `solution_frame_serial_four_span_axial` | `FX=100,000 N` | `100,000` | 30 | 4 | 24 | 468 | 4 |
| `high_load_frame_serial_five_span_axial_100kn` | `solution_frame_serial_five_span_axial` | `FX=100,000 N` | `100,000` | 36 | 5 | 30 | 576 | 5 |

각 slot은 다음을 재생한다.

- ModelIR에서 nodal load와 provenance만 바뀌는 exact derivative
- `global_load`의 exact scale
- DOF/constraint/CSR/scatter/stiffness/recovery를 포함한 16개 plan array의 parent byte equality
- `symbolic_reuse_hash`, `partition_hash`, `ordering_hash`, `recovery_operator_hash`, `policy_hash` equality
- CPU FGMRES `3/3` convergence와 solver/authoritative tolerance 통과
- parent와 동일한 restart-cycle shape
- dense direct solution과 CPU solution의 선형 load scaling

Registry loader에는 caller path나 override가 없다. Root registry, schema, 세 model resource의 package bytes를 고정하며 weak-key transaction은 exact object, snapshot hash, resource digest를 결속한다.

## 3. ResultIR v3 aggregate

Aggregate factory는 정확히 세 개의 이미 발행된 `HipFgmresResultIRResultV3`만 받는다. 입력 순서는 자유지만 source execution-plan hash를 registry와 대조한 뒤 registry 순서로 canonicalize한다.

케이스별 교차 결속 대상은 다음과 같다.

- registry slot/parent/registration/model bytes/load scale
- ModelIR content, ExecutionPlan, CPU result
- model-case parity, terminal metric parity
- terminal observation, completion export payload/receipt
- runtime device identity와 `gfx1030`
- accepted/trial/committed StateIR lineage
- solution/exported residual payload
- `exported HIP -> independent math.fsum -> ResultIR plan F-Ku` 두 componentwise receipt
- retained base ResultIR v2, fixed-physics witness, reaction/member force/energy result arrays

Aggregate 자체의 고정 총량은 다음과 같다.

- `3 ResultIR v3 ready`
- `0 retained base ResultIR v2 ready`
- `3 committed StateIR`
- `G=78`, `E=10`, `F=60`, `nnz=1,188`
- 결과 배열 `18개`, `3,392 bytes`
- retained completion payload `6개`, `960 bytes`
- aggregate가 직접 추가한 device operation/D2H/solve/export/fallback은 모두 `0`

Aggregate receipt의 actual backend 표시는 세 child source가 exact ResultIR v3 factory에서 검증한 HIP provenance를 뜻한다. Aggregate가 새 GPU 계산을 수행했다는 뜻은 아니다.

## 4. 권한과 위조 방지 경계

- Registry schema는 manifest 전체를 `const`로 고정한다.
- Registry transaction과 aggregate issuance는 weak-key exact identity를 사용하며 clone은 권한을 상속하지 않는다.
- Aggregate는 direct construction, duplicate plan, unissued child clone, issuance transplant, row reorder, unknown field, promotion claim 변조를 fail-closed한다.
- Serialized aggregate receipt만으로 process-local child provenance를 재생성할 수 없다.
- 원래 HIP context를 닫은 뒤에도 정확한 child ResultIR v3 객체와 issuance가 살아 있으면 sparse physics와 aggregate를 다시 검증할 수 있다.
- Aggregate module은 native runtime, HIPRTC, device identity attestor, CPU solve, ResultIR builder를 직접 호출하지 않는다.

## 5. 검증 결과

### 5.1 Registry 및 aggregate 계약

- registry contract: `7 passed in 89.71s`
- deterministic generator check:
  - raw `sha256:7411b02b72500b7448ed97dd3470d27e8fb129a7d98ee600b2ff06374a1b113d`
  - canonical `sha256:72ea556471edb72a2262f870e76d4fc423e9d665da82f6d8e4d03dd6ae953f9e`
  - schema `sha256:5883c16075f8ebabdc7e8a6dfdb2b300e3c89973cc14ea6e955bbd1d16f9ac75`
- aggregate contract: `6 passed in 344.33s`, peak RSS `133,608 KiB`
- public API / wheel resource / isolated registry replay: `2 passed in 38.97s`
- capability matrix: `15 passed in 0.33s`
- registry + aggregate + public + capability focused cross-check:
  `30 passed in 475.00s`, wall `475.54s`, peak RSS `134,724 KiB`
- v0.2.45-v0.2.50 DiagnosticIR/all-converged/roundoff/model-case/ResultIR adjacent regression:
  `228 passed in 751.26s`, wall `751.94s`, peak RSS `142,288 KiB`
- Ruff, `py_compile`, JSON Schema Draft 2020-12, hardware test collection 통과
- single dirty non-release wheel:
  - `1,497,757` bytes, `296` members
  - `sha256:1e0d420db65e36d9c3908d6f09b5d0285ff37f6d1c57e2d6cbe621b8a99c6da7`
  - high-load fixture JSON `4`개와 신규 module/schema exact bytes 포함
  - 격리 설치 public symbols `996/810/93/10`
  - source tree를 import path에서 제거한 설치에서 registry `3` slot, canonical/receipt hash 전수 재생

이 wheel은 현재 dirty source의 단일 build smoke이며 reproducible 또는 authoritative release artifact 증거가 아니다.

### 5.2 실제 로컬 RX 6900 XT `gfx1030`

Required 실행:

```bash
PYTHONPATH=src \
ENGINE_V2_REQUIRE_FGMRES_MODEL_CASE_PARITY_V2_HARDWARE=1 \
python3 -m pytest -q -s \
  tests/test_engine_v2_fgmres_model_case_parity_v2_hardware.py
```

결과:

- `1 passed in 556.64s (0:09:16)`
- wall `557.28s`
- process peak RSS `432,500 KiB`
- recurrence blocking D2H `0`
- completion export blocking D2H `9 attempts / 9 success / 0 failure`
- fallback `0`
- 실행 전후 source aggregate 동일:
  `sha256:502e29bb785809b6a028b9fb331a53f984a1ed1656511ddc9ebdc05e1ecd4f10`

발행 identity:

- registry receipt: `sha256:b081452dfa93af8f342a8e59e85e7ee53b397e01757ba6c5e5fe63e75e1dfbf3`
- aggregate attestation: `sha256:b2d7ed6b2c3e47c93bce65daf6a00883da43cd213ee6cafb7bd9f1ee0494d65f`
- aggregate receipt: `sha256:a2ffc001def91eb5347da6f799e725d1abebc83a20b0667a93b053d34219e3f3`

| slot | ResultIR v3 receipt | 최대 terminal ratio |
| --- | --- | ---: |
| rotated `10 kN` | `sha256:3dd4b7d51b650fc6932f03ccc73d497919763aeb46ee02c648c56afeab71e3ff` | `0.0023069006688603657` |
| four-span `100 kN` | `sha256:bc36f3bfcd99a2b7bd4b08f12155fba5c7fcc8ea1e70765a32a35e40d077f364` | `0.002952072072072049` |
| five-span `100 kN` | `sha256:e54320ca456a36a5f88f150e6a49c03c08a058013008d5a32871256d1051d7e5` | `0.00021165239437481313` |

## 6. Claim boundary

이번 milestone이 증명하지 않는 항목:

- general multi-restart history v2와 per-restart checkpoint vector ABI
- estimated-residual / solution-update roundoff model
- frozen ResultIR v2 fixed residual-sign policy에서의 원래 고하중 ready 승격
- standalone serialization provenance, persistent external log, signed evidence
- 외부 `gfx1100`, multiarchitecture 또는 동일 artifact의 두 ISA parity
- process-wide ROCm activity completeness나 broad host-copy-zero
- GPU-native reaction/member-force/energy recovery
- end-to-end O(N), 성능 우위 또는 speedup
- nonlinear, dynamic, shell, solid, contact
- promotion eligibility 또는 commercial readiness

## 7. 다음 단계

1. completion ABI에 per-restart checkpoint solution/true-residual vector를 추가하고 general history v2를 별도 계약으로 구현한다.
2. `gfx1100` 외부 hardware runner와 서명·지속 로그를 통해 architecture 및 provenance 범위를 넓힌다.
3. 현재 CPU sparse recovery를 device recovery로 이동하되 ResultIR 물리 replay와 fallback telemetry를 보존한다.
4. FGMRES 이후 AMG/DD 전처리와 bounded near-linear scaling gate로 Phase 0의 다음 수치해석 병목을 진행한다.
