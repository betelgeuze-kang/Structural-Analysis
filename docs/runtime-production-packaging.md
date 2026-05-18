# Runtime Production Packaging Runbook

- 기준일: 2026-05-18
- 상태: runtime packaging gate ready, installer/container hardening still required
- 목적: solver/runtime evidence를 독립 상용제품 배포 단위로 승격하기 위한 패키징, 호환성, 지원 번들 기준을 고정한다.

## Current Boundary

P0/P1 evidence는 closed/ready이고, runtime packaging gate는 `scripts/build_runtime_packaging_manifest.py` 산출물 기준 ready다. Strict runtime path는 실제 producer -> runtime -> verifier evidence와 package compatibility manifest를 함께 요구하며, 현재 `zero_copy_real_probe_report_strict.json`와 runtime packaging manifest가 이 조건을 충족한다.

## Required Artifacts

| Artifact | Required fields |
| --- | --- |
| `production_runtime_packaging_manifest.json` | runtime version, backend list, CPU/GPU policy, supported OS/driver, model/data artifact contract, compatibility matrix |
| `support_bundle_manifest.json` | audit log, version, license status, runtime probe, EB/RH receipts, viewer report, package SHA, redaction policy |
| strict runtime probe | real producer path, host-copy metrics, CPU fallback flag, verifier result |
| SBOM/license report | dependencies, native artifacts, third-party license status |
| rollback notes | package rollback and evidence restore steps |

## Current Evidence

```bash
python3 scripts/build_runtime_packaging_manifest.py --json
python3 scripts/build_support_bundle.py --json
python3 scripts/check_independent_product_readiness.py --json
```

- Runtime package manifest: `implementation/phase1/production_runtime_packaging_manifest.json`
- SBOM: `implementation/phase1/runtime_sbom.json`
- Native artifact manifest: `implementation/phase1/native_runtime_artifact_manifest.json`
- Compatibility matrix: `implementation/phase1/runtime_version_compatibility_matrix.json`
- Support bundle manifest: `implementation/phase1/support_bundle_manifest.json`

## Closure Criteria

1. `zero_copy_real_probe_report_strict.json` or approved production backend strict report passes without silent CPU fallback.
2. Runtime package manifest is complete and `contract_pass=true`.
3. Support bundle manifest is complete and `contract_pass=true`.
4. SBOM/license evidence is generated for Python, Node, and native runtime assets.
5. Clean checkout can reconstruct release evidence without private local state.

## Packaging Modes

| Mode | Current policy |
| --- | --- |
| SaaS | Requires production ops/security runbook and tenant isolation tests |
| On-prem | Requires installer/container, offline license, update channel, support bundle |
| Air-gapped | Requires artifact cache, no external network dependency, signed update package |

## Current Gate Status

This runbook and the generated manifests close the runtime packaging/support blockers in the independent product gate. The product gate should still remain blocked until strict EB/RH receipt and closure evidence are attached.
