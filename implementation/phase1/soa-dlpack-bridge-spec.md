# SoA 기반 DLPack 브릿지 스펙 (Step 4)

목표: Rust/HIP 메모리를 AoS가 아닌 SoA로 강제하여 PyTorch contiguous tensor와 1:1 매핑.

## 메모리 레이아웃
- 금지: AoS (`[{x,y,z}, {x,y,z}, ...]`)
- 필수: SoA (`x[]`, `y[]`, `z[]`, `mass[]`, `support_mask[]`)

## 계약 필드
- `layout`: `SoA`
- `dtype`: `float32` (mask는 `uint8` 허용)
- `contiguous`: `true`
- `device`: `hip` 또는 `cpu` (개발모드)
- `dlpack_capsule_name`: `dltensor`

## 브릿지 산출물
- `soa_dlpack_contract_report.json`
  - `layout_pass`
  - `tensor_fields`
  - `zero_copy_expected`
  - `reason_code`

## reason_code
- `PASS`
- `ERR_LAYOUT_NOT_SOA`
- `ERR_NON_CONTIGUOUS`
- `ERR_DTYPE_UNSUPPORTED`
