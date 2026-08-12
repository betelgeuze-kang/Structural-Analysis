# Native CI Contract

Status: implementation-ready design

Scope: Rust, C++, C ABI and optional ROCm/HIP migration

## 1. Objectives

- ordinary native PR feedback is terminal within 15 minutes
- exact merge-ref product integration is separated from slow legacy/evidence suites
- hardware execution uses only an already-configured dedicated lane
- cancelled/superseded runs never count as latest-head evidence
- no workflow silently starts or mutates a runner service

## 2. Required lanes

### pr-fast

Trigger: every pull_request, merge_group and push to main. The scope classifier marks
non-native changes not applicable so the two required contexts are still reported instead
of remaining Pending because a path-filter skipped the whole workflow.

Budget: each job 10 minutes, required aggregate within 15 minutes

Runner: GitHub-hosted Linux CPU

Jobs:

1. scope-contract
   - changed-path classification
   - generated/bindings drift
   - protected evidence unchanged assertion
2. rust-quality
   - cargo fmt --check
   - cargo clippy --workspace --all-targets with warnings denied
   - cargo test --workspace for pure Rust/unit targets
   - locked dependency graph compiles with the declared Rust 1.77 minimum toolchain
   - R3 bounded track CPU ownership, ABI v1.2/safe-wrapper integration and C1 claim check
   - four-case 9-node Python product-golden SHA-256 matrix and frozen legacy endpoint-only
     divergence check
   - R3 nonlinear static CPU ownership, ABI v1.3/safe-wrapper integration and C1 claim check
   - R3 nonlinear NDTHA shared constitutive ownership, ABI v1.4/safe-wrapper integration and C1
     claim check
   - nonlinear-static independent dense-matrix Python oracle, five-case product-golden SHA-256
     matrix, frozen byte-identical legacy 3-story copy and nonconvergence taxonomy check
   - nonlinear-NDTHA independent dense-matrix Python oracle, strict five-case product-golden wire,
     all 11 response channels, adaptive/collapse taxonomy and frozen legacy config/input check
   - retained R2 raw/wire/adapter ownership and neutral fixture SHA-256 checks
   - retained R1 ABI v3 layout/numerical golden tests and exact release cdylib export set
3. cpp-quality
   - CPU-only CMake configure
   - build with warnings as errors
   - CTest unit suite
4. abi-contract
   - public header compile as C11 and C++20
   - Rust/C layout, constants and struct_size compatibility
   - invalid pointer/length/stride/overflow and failure atomicity
   - R3 legacy-runtime changes are classified as ABI/runtime scope; their frozen binary export
     check remains in rust-quality because the compatibility library is a Rust cdylib
   - track config/output pointer, length, stride, alignment, overlap and nonconvergence atomicity
   - nonlinear static five-input/output pointer, length, stride, alignment, finite, overlap and
     nonconvergence atomicity
   - all three solver operations run in ABI CTest; unavailable v1.0-v1.3 table tails remain null
5. modelir-golden
   - Rust wire capability: bounded positive/negative fixtures and canonical bytes/hashes
   - C++ semantic CTest is required with `--no-tests=error` after the bounded
     `modelir_v2_cpp_core` capability is promoted; aggregate Rust/CLI claims remain separate
6. dependency-boundary
   - Rust crate and CMake target cycle/owner rules
   - native product source must not import/call Python
   - locked SPDX alternatives and dependency MSRV satisfy the native policy
7. pr-fast aggregate
   - requires every applicable job success
   - skipped required child is failure unless path classifier proves not applicable

pr-fast는 full Python collection, LFS evidence materialization, browser, external solver와
hardware를 실행하지 않는다.

## 3. merge-product

Trigger: pull_request on the exact current merge ref after pr-fast

Budget: 45 minutes hosted CPU

Runner: GitHub-hosted Linux CPU; optional OS matrix는 별도 non-blocking lane

Required jobs:

1. build-package
   - clean Cargo/CMake release build
   - shared/static link smoke와 package metadata/ABI identity
2. rust-cpp-integration
   - safe wrapper ownership, concurrency와 exception/panic conversion
   - bounded track/nonlinear-static C++/Python product-golden parity and fallback count 0
   - legacy Rust displacement/residual/interior parity와 frozen endpoint-only divergence
3. python-oracle-parity
   - focused existing Python oracle only
   - canonical bytes/hash, error taxonomy와 bounded numerical vectors
   - track full-vector product golden parity; legacy endpoint convention remains separately frozen
   - nonlinear-static dense-matrix full-result matrix와 nonconvergence taxonomy parity
   - nonlinear-NDTHA dense-matrix full-result/adaptive/collapse matrix와 nonconvergence taxonomy
     parity
4. checkpoint-restart
   - exact model/state/execution hash binding
   - cancel/crash/restart and mismatch rejection
5. bounded-product-e2e
   - CLI/API input -> C++ core -> ResultIR/ReportIR output
   - no unsupported authority promotion
6. merge-product aggregate
   - latest exact-head and merge-ref only

Python oracle timeout/cancellation은 parity success가 아니다. merge-product가 요구하는
fixture의 LFS object가 없으면 fail closed하며 pointer text를 data로 읽지 않는다.

## 4. Full, evidence and hardware lanes

### nightly-full

- full Python suite, broader cross-platform and sanitizer matrix
- legacy compatibility/deprecation audit
- not an automatic substitute for pr-fast or merge-product

### evidence/manual

- protected productization receipt validation
- external solver/source and legal/operator attachment
- explicit workflow_dispatch inputs and exact commit identity

### hip-dedicated

Trigger: workflow_dispatch or approved PR label after hosted gates are green

Runner: exact preconfigured labels and verified device target only

Forbidden: generic service install/start/mutation, implicit gfx1100, silent CPU fallback

Required preflight:

- exact commit and merge-ref identity
- ROCm runtime/compiler and device architecture
- fp64/sparse/device reduction capability
- clean worktree and required LFS materialization
- workflow target allowlist

Required receipt:

- source/tree hash, workflow/run/job identity
- device/architecture/driver/runtime/compiler
- precision/deterministic policy
- H2D/D2H bytes, synchronization count, resident buffer inventory
- CPU fallback count 0
- CPU/HIP parity and tolerance
- cold/warm timing and peak VRAM where performance is claimed

Hardware queued 상태는 external runner boundary로 따로 보고하고 hosted pending과 합치지
않는다.

## 5. Context names and branch protection

Initial required contexts:

- native-pr-fast
- native-merge-product

각 context는 aggregate job 하나만 ruleset에 연결하고 child job 목록은 workflow contract
test가 검증한다. context를 rename하거나 required child를 줄이는 변경은 별도 workflow
contract PR과 exact-main 검증을 요구한다.

HIP context는 첫 hardware-capable product slice가 선언된 뒤 scope별로 추가한다. 단순
workspace/ModelIR PR에는 hardware context를 요구하지 않는다.

## 6. Change routing

| Changed path | pr-fast | merge-product | HIP |
| --- | --- | --- | --- |
| docs/native, ADR only | contract/link lint | 불필요 | 불필요 |
| native/contracts, ABI header | 전체 | ModelIR/ABI integration | 불필요 |
| native/cpp model/elements/materials | 전체 | CPU oracle/product E2E | 관련 kernel이 있으면 별도 |
| native/cpp/hip | host compile contract + CPU tests | CPU integration | dedicated required |
| native/runtime/report/cli | Rust + ABI | restart/E2E | backend selection 변경 시 |
| Python oracle fixture | golden + focused Python | oracle parity | numerical fixture면 관련 |
| protected evidence | 별도 evidence workflow | native aggregate로 승격 금지 | authorized scope만 |

## 7. Cancellation and historical results

- concurrency group은 workflow + PR number를 사용하고 새 head에서 old run을 cancel한다.
- cancelled, skipped, neutral과 superseded SHA failure는 latest-head pass/fail count에서
  분리한다.
- manual rerun은 source/head가 동일해도 원인과 authorization을 기록한다.
- unrelated queued job을 새 native PR 때문에 수동 재실행하지 않는다.

## 8. Workflow contract tests

- every job has timeout-minutes
- hosted lane uses fixed hosted runner label
- hardware lane has allowlisted self-hosted labels and exact target preflight
- checkout LFS option is explicit for fixture-consuming jobs
- required aggregates reference all declared children
- pr-fast contains no full/evidence/hardware command
- merge-product uses exact merge ref and reports head/base/tree
- no workflow command installs, enables or starts runner service

## 9. Rollout order

1. current milestone PR chain closes and latest main is fetched
2. separate gate-bootstrap PR adds pr-fast and merge-product contracts
3. native workspace foundation consumes the new contexts
4. ModelIR slice enables golden/oracle jobs
5. first HIP product slice adds dedicated hardware context

문서와 workflow skeleton 준비는 병렬 가능하지만 ruleset 변경과 required context 적용은
현재 chain 종료 후 수행한다.

## 10. Gate-bootstrap implementation mapping

- `.github/workflows/native-pr-fast.yml` owns both direct aggregate jobs named
  `native-pr-fast` and `native-merge-product`. Keeping both jobs direct preserves the exact
  ruleset context names; a reusable workflow would expose a compound check name.
- merge-product children depend on the successful pr-fast aggregate and execute on the same
  checked-out `github.sha`. Pull-request runs verify the exact base/head parents; merge-queue
  runs verify the merge-group SHA and base ancestry.
- `scripts/classify_native_ci_scope.py` computes language/domain applicability and rejects any
  protected-evidence path included in a native change set.
- `.github/workflows/native-nightly-quality.yml` owns ASan/UBSan, bounded libFuzzer smoke and
  locked dependency/SPDX policy checks. Once `native/Cargo.toml` exists, missing sanitizer,
  fuzz or dependency-policy ownership fails closed.
- no hosted workflow invokes HIP/ROCm. `hip-dedicated` remains deferred until the first actual
  HIP product slice can name its execution target and receipt schema.

이 mapping은 workflow topology 구현만 뜻한다. workspace, ABI, ModelIR, sanitizer/fuzzer
실행 성공 또는 hardware evidence를 주장하지 않는다.
