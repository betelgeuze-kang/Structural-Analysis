# Strict Rust/HIP Producer Command Template

모바일/저사양 환경에서는 실제 실행 없이 아래 템플릿만 문서화하고, CI/HPC에서 실제 값을 채웁니다.

## Required contract
- command must return JSON on stdout
- fields:
  - `strict_rust_hip_pass` (bool)
  - `runtime_kind` (`rust_hip` expected in strict mode)
  - `host_copy_bytes` (number, expected 0)
  - `shared_storage` (bool)

## Template
```bash
python implementation/phase1/zero_copy_real_probe.py \
  --producer-cmd "<RUST_HIP_PRODUCER_CMD> --mode dlpack_probe" \
  --require-rust-hip \
  --out implementation/phase1/zero_copy_real_probe_report_strict.json
```

## Checklist
1. Producer writes valid JSON (single object).
2. `runtime_kind` is `rust_hip`.
3. `strict_rust_hip_pass` is `true`.
4. `host_copy_bytes` is `0`.
5. Report archived in CI artifact list.
