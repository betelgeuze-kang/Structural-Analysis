# Global Authority Two-Track

## Decision
- Track A: Global Authority Validation (SAC/OpenSees/NHERI)
- Track B: Product Throughput (single 6900 XT production path)

Both tracks run in parallel, but release promotion depends on Track A first.

## Track A (Authority)

### A1. OpenSees baseline (immediate)
- Input: public OpenSees `.tcl` models.
- Gate:
  - parser contract pass
  - real topology source only
  - shell/beam mix required for megastructure class

### A2. SAC benchmark (strict real-source only)
- Input: curated SAC/FEMA model manifest + reference response metrics.
- Gate:
  - source provenance + hash pin
  - holdout split enforced
  - drift/base shear/mode metrics <= 5% target band

### A3. NHERI physical test correlation
- Input: published NHERI sensor time-history datasets.
- Gate:
  - direct metric source only (no inferred-only pass)
  - phase-aware waveform error + residual drift checks
  - convergence ratio 100% in enforced stage

## Track B (Product Throughput)
- Keep current single-GPU strict mode (`gpu_strict=true`, no CPU fallback).
- Maintain scale-out/partition/noise gates as deployment blocker.

## Promotion Policy
- RC eligible only if:
  - Track A gate PASS
  - existing phase1 CI gate PASS
- Nightly must include Track A artifacts as required inputs.

