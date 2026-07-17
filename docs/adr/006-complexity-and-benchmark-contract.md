# ADR-006: Complexity and Benchmark Contract

- Status: accepted
- Date: 2026-07-10
- Deciders: Engine v2 architecture baseline

## Context

비어텐션, sparse operator 또는 직교사영 사용만으로 전체 해석이 O(N)이 되지는 않는다. 반복 수, rank, time step, 후보 수와 dense 변환을 숨기면 성능 주장이 왜곡된다.

## Decision

- `N=free DOF`, `E=mesh incidence`, `T=time steps`, `B=design candidates`, `k=coarse/correction rank`로 정의한다.
- residual/JVP와 고정 깊이 local AI pass는 bounded degree/width/depth에서 `O(N+E)`로 제한해 주장한다.
- 전체 solve는 mesh-independent iteration이 실측될 때만 near-O(N)이라 표현한다.
- 최소 5개 크기군에서 cold/warm time, RAM/VRAM, transfer, iteration, operator complexity를 측정한다.
- 목표 time/memory log-log slope는 `0.85-1.15`, mesh 증가 시 Krylov iteration 증가는 `<=20%`다.

## Normative invariants

- dynamic solve는 `O(T(N+E))`, candidate batch는 `O(B(N+E))`로 보고한다.
- `P=QQ^T`, full sparse-to-dense, global all-pairs attention을 금지한다.
- rank/depth/width가 크기와 함께 증가하면 O(N) 결과로 집계하지 않는다.
- synthetic loop만으로 end-to-end complexity를 증명하지 않는다.

## Alternatives considered

- 단일 10M DOF 추정 receipt: 실제 full solve scaling을 증명하지 못해 기각.
- 한 크기의 GPU speedup: asymptotic/메모리 특성을 설명하지 못해 기각.

## Verification

- 5-size log-log regression
- dense/fallback static guard
- end-to-end graph -> AI -> residual replay benchmark
- 16GB VRAM OOM/fallback gate

## Rollback / supersession

목표 slope를 완화할 때는 해당 element/analysis family와 병목 증거를 명시한 새 ADR이 필요하다.
