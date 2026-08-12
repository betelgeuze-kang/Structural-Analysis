# First Native Slice: ModelIR v2 Contract and ABI Round-trip

Status: Slices A-C implemented; Slice D pending

Implementation status: Slice B promotes `modelir_v2_rust_wire` at C1. Slice C promotes the
bounded `modelir_v2_cpp_core` at C0: exhaustive typed descriptor transport, deep-copy ownership,
C++ semantic validation, report/snapshot ABI and native tests. The aggregate `modelir_v2`
capability remains planned until Slice D supplies the safe Rust wrapper, cross-language oracle
parity, round-trip hash verification and CLI validation.

Depends on: ADR-002, ADR-009 and workspace-and-abi-v1.md

## 1. Outcome

한 ModelIR v2 JSON document를 Rust가 strict decode/canonicalize하고, C ABI descriptor로
C++ ModelIR owner에 전달한 뒤, C++ semantic snapshot을 Rust가 다시 canonical
projection으로 직렬화한다. 성공 시 original과 round-trip의 content, semantic과
provenance hash가 정의된 범위에서 일치해야 한다.

이 slice는 모델 contract와 language boundary만 검증한다. element stiffness, assembly,
solve, engineering result, HIP execution 또는 G1 closure를 주장하지 않는다.

## 2. Ownership

### Rust structural-contracts

- UTF-8 JSON read와 duplicate-key rejection
- JSON Schema draft 2020-12 validation
- strict number typing, finite number와 signed-zero normalization
- deterministic canonical JSON bytes
- content, semantic와 provenance SHA-256
- wire DTO와 C descriptor builder
- validation report와 stable error serialization

### C++ structural_model_ir

- deep-copied immutable in-memory ModelIR
- canonical SI unit/scale consistency
- stable ID uniqueness와 reference integrity
- element end-node distinction/effective length
- constraint and prescribed-value consistency
- load-pattern/reference and load-combination acyclicity
- time-function monotonicity
- roundtrip_map entity-kind integrity
- blocking unsupported feature와 analysis-ready separation
- caller-owned snapshot export

C++는 JSON text를 product hot path에서 parse하거나 canonicalize하지 않는다. Rust는
C++ semantic validation을 다시 구현해 독립 solver truth를 만들지 않는다. transition
기간에는 Python oracle 결과와 세 구현의 issue set을 비교한다.

## 3. Compatibility source

첫 implementation은 다음 Python behavior를 byte/status oracle로 사용한다.

- src/structural_analysis/model_ir/validation.py
- src/structural_analysis/model_ir/loader.py
- src/structural_analysis/model_ir/types.py
- src/structural_analysis/schemas/model_ir_v2.schema.json

generic JSON canonicalization 표준으로 조용히 바꾸지 않는다. 특히 number rendering,
Unicode ordering, signed zero와 semantic/provenance projection은 existing golden
bytes/hash와 일치해야 한다. 향후 canonical format 변경은 schema major migration
report가 필요하다.

## 4. Minimum typed surface

첫 slice는 schema의 다음 family를 모두 typed descriptor로 운반한다.

1. document identity: schema_version, model_id, capability_profile
2. units and conversion factors
3. coordinate system and DOF components
4. nodes
5. materials and parameters
6. sections and properties
7. elements, local axis, offsets and releases
8. constraints and prescribed values
9. load patterns and nodal components
10. load combinations and factors
11. time functions
12. construction stages
13. provenance
14. roundtrip map
15. unsupported features and namespaced extensions

unknown field를 generic map으로 숨기지 않는다. schema가 허용한 extensions만 opaque
canonical JSON bytes로 보존할 수 있고, core solver는 extension을 소비한다고
주장하지 않는다.

## 5. ABI call sequence

~~~text
Rust bytes
  -> strict decode/schema validation
  -> canonical bytes + three hashes
  -> Rust-owned descriptor arena
  -> sa_model_ir_create_v1
       C++ descriptor validation + deep copy + semantic validation
  -> immutable sa_model_ir_handle_v1
  -> sa_model_ir_validation_report_v1
  -> sa_model_ir_snapshot_size_v1
  -> sa_model_ir_snapshot_v1(caller-owned buffers)
  -> Rust projection reconstruction
  -> deterministic canonicalization/hash comparison
  -> sa_model_ir_destroy_v1
~~~

Rust descriptor arena와 모든 borrowed string/array는 create return까지 유지한다.
C++ handle은 descriptor pointer를 보존하지 않는다. snapshot 함수는 partial success를
허용하지 않는다.

## 6. Stable result

successful parse/create는 최소 다음 값을 제공한다.

- schema_version, model_id와 capability_profile
- analysis_ready
- sorted blocking_feature_ids와 derived_blocking_feature_ids
- sorted validation issue tuples: code, JSON pointer path, log-safe detail
- content_hash, semantic_hash와 provenance_hash
- entity family counts
- ABI/library build identity

hash algorithm은 sha256: 접두사와 lowercase hex를 사용한다. validation issue ordering은
path, code, detail의 stable order로 고정한다.

## 7. Positive fixtures

첫 gate는 다음 tracked fixtures를 사용한다.

- tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json
- examples/bounded_planar_frame_alpha.model-ir.v2.json
- examples/bounded_planar_settlement.model-ir.v2.json
- examples/bounded_frame3d_direct_control.model-ir.v2.json
- examples/bounded_frame3d_direct_control_axial_yield.model-ir.v2.json
- examples/bounded_frame3d_direct_control_ry_bending.model-ir.v2.json
- examples/bounded_frame3d_direct_control_rz_bending.model-ir.v2.json
- examples/bounded_frame3d_direct_control_torsion.model-ir.v2.json

fixture는 LFS materialization이나 protected release evidence에 의존하지 않아야 한다.

## 8. Negative fixture matrix

| Case | Expected boundary |
| --- | --- |
| duplicate JSON key | Rust decode fail, C++ 호출 없음 |
| root is not object | schema invalid |
| unknown non-extension field | schema invalid |
| bool used as integer/number | schema invalid |
| NaN, Infinity, -Infinity | decode/finite fail |
| signed negative zero | canonical normalization and golden hash |
| unit symbol/scale mismatch | semantic invalid |
| duplicate family index or ID | semantic invalid |
| dangling node/material/section/reference | semantic invalid |
| same element end nodes or zero effective length | semantic invalid |
| prescribed DOF not restrained/conflicting restraint | semantic invalid |
| all-zero required load | semantic invalid |
| load combination cycle | semantic invalid |
| non-monotonic time function | semantic invalid |
| roundtrip entity-kind mismatch | semantic invalid |
| blocking unsupported feature | contract valid, analysis_ready false |
| truncated descriptor/ABI mismatch | ABI error before allocation |
| invalid string/slice pointer-length | invalid argument before allocation |
| undersized output buffer | required size, no partial output |

각 case는 Python report, Rust pre-validation 또는 C++ report 중 어느 boundary가 owner인지
test 이름에 명시한다.

## 9. Round-trip invariants

- successful original canonical bytes는 Rust decode -> encode 후 byte-identical하다.
- C++ snapshot으로 재구성한 semantic projection hash는 original semantic hash와 같다.
- provenance와 extension을 snapshot 범위에 포함한 경우 provenance hash도 같다.
- entity order는 canonical index/id contract를 보존하고 unordered container iteration에
  의존하지 않는다.
- analysis_ready false를 error success로 바꾸지 않는다. contract validity와 solver
  readiness를 별도 field로 유지한다.
- failed create에서 live handle count와 caller output는 호출 전과 같다.

## 10. Test layers

### Native unit

- Rust strict decode/canonicalizer/hash tests
- C++ units/reference/cycle/unsupported validation tests
- C and C++ ABI header/layout tests
- safe Rust RAII/drop/error mapping tests

### Cross-language parity

- Python/Rust canonical bytes and three hashes
- Python/C++ issue code/path sets
- Rust descriptor -> C++ snapshot -> Rust semantic hash
- old minimum struct_size and current full struct compatibility

### Integration

- cargo test starts a CPU-only C++ ABI test library
- exact fixture batch has deterministic results across repeated processes
- concurrent immutable handle query is race-free
- invalid concurrent mutation/destroy is rejected

### Product boundary

- structural-cli model validate emits the versioned report
- non-ready model exits nonzero only when require-analysis-ready is selected
- report never claims solver, HIP, engineering-result or commercial readiness

## 11. CI acceptance

The slice is merge-eligible only when:

1. pr-fast is green within 15 minutes.
2. merge-product validates every positive/negative fixture on the exact merge ref.
3. Python oracle parity is zero-diff or every intentional delta has a schema-major migration
   decision.
4. CPU-only hosted build has no ROCm runtime dependency.
5. sanitizer lane reports no leak, invalid access or cross-boundary allocator misuse.
6. protected evidence bytes are unchanged.
7. the Python ModelIR path remains available as oracle/rollback.

## 12. PR decomposition

- Slice A: Cargo/CMake workspace, C ABI base types, error/lifetime/layout tests
- Slice B: Rust strict ModelIR wire/canonicalization and Python oracle parity
- Slice C: C++ typed ModelIR, semantic validator and snapshot ABI
- Slice D: Rust safe wrapper, round-trip integration and structural-cli validate command

각 slice는 이전 slice를 normal dependency로 사용하고 독립 draft PR/gate를 유지한다.
한 PR에서 Python 제거 또는 HIP execution을 함께 수행하지 않는다.
