# Engine v2 CPU Reference Linear Static v1

- Implementation: [`linear_static.py`](../src/structural_analysis/engine_v2/backends/cpu_reference/linear_static.py)
- Input ABI: [`SolverModelBuffers v1`](../src/structural_analysis/engine_v2/buffers.py)
- Golden model: [`frame_cantilever_all_modes.json`](../tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json)
- Analytic expected values: [`frame_cantilever_all_modes.expected.json`](../tests/fixtures/model_ir_v2/frame_cantilever_all_modes.expected.json)
- Authority: [ADR-001](adr/001-numerical-truth-and-claim-boundary.md), [ADR-003](adr/003-operator-abi-and-constitutive-source-policy.md)

## Supported numerical contract

- FP64, SI units
- node-major `UX, UY, UZ, RX, RY, RZ`
- 3D Euler-Bernoulli frame
- linear 3D truss assembly contract
- isotropic linear elastic material
- dense NumPy reference solve
- SciPy sparse parity solve
- residual `R(u)=Ku-F`
- exact linear JVP `Jv=Kv`
- local end-force recovery와 strain energy

## Local frame

element local x는 i->j 방향이다. global Z를 우선 reference로 사용하고 평행에 가까우면 global Y를 선택한다. local y/z는 right-handed orthonormal frame으로 만들고 `local_axis_rotation_rad`를 local x 주변에 적용한다.

## Golden analytic cases

2 m cantilever, `E=200 GPa`, `A=0.02 m2`, `Iy=8e-5 m4`, `Iz=5e-5 m4`, `J=1e-5 m4`에 대해 다음을 고정한다.

| Case | 핵심 결과 |
| --- | --- |
| Axial | `UX=5e-5 m`, base `FX=-100000 N` |
| Weak-axis bending | `UY=-0.0026666666667 m`, `RZ=-0.002 rad`, base `FY=10000 N`, `MZ=20000 N*m` |
| Strong-axis bending | `UZ=-0.0016666666667 m`, `RY=0.00125 rad`, base `FZ=10000 N`, `MY=-20000 N*m` |
| Torsion | `RX=0.013 rad`, base `MX=-5000 N*m` |

추가 검증은 dense/sparse parity, stiffness symmetry/SPD, centered finite-difference JVP, 공간회전+roll, 2요소 assembly, immutable result buffer를 포함한다.

## Explicit exclusions

- non-zero rigid offset
- element end release
- non-zero prescribed displacement/rotation
- self weight generation
- load combination, time function, construction stage
- Timoshenko shear deformation
- shell, solid, contact
- geometric/material nonlinearity
- mass, damping, eigen, dynamic solve
- HIP parity 또는 commercial readiness claim

제외 기능은 무시하지 않고 ModelIR buffer profile 또는 CPU reference preflight에서 fail-closed 한다.
