# Fixed full-history 1,024-layer refinement protocol

The retained 256/512 comparison leaves 27 of 240 concrete field groups outside the original exploratory 1% screen, all tensile damage. The next numerical observation uses 1,024 concrete layers and compares to the original complete 512-layer path. It does not change the public API, the numerical engine, material parameters, reinforcement, geometry, force vector, targets or solver tolerances.

Numerical source remains `3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`, checked against all 461 original source files and their Git blobs. The original input checksum remains `34822feaee8f569712b46e5842f5fcc3253a9a851bb9a13c92624be238b4c23e`. Execute the complete forty targets from 2 to 80 mm at control DOF 15 with the original proportional force vector. This is not constant axial loading. One run, no numerical retries or tolerance changes.

The 1,024-layer protocol bytes must hash to `e620f118fc72a7af34b8a527649dcddc3d1b78902922aab2860baa92ba73432b` before solving. The reference 512-layer result hash is `2e5974645b6f6fbc81eb8f647a9d6af049007856a466e50bc41b6f685d3fbfd3`; its protocol hash is `9e1ede09c94df2402765f8980d1c6d514dc71d87c23dc13312c7130c9e787f96`.

The read-only comparison retains the original 400 nodal/steel and 240 concrete groups, equal-area projection, local maxima and witnesses. It reads/validates/extracts one full path and releases it before opening the other. File limits are 4 GiB for the retained coarse result and 8 GiB for the fine result; they are file-size limits, not memory-usage estimates. Failed paths are rejected before comparison. No material-field averaging replaces the original local error screen.

Focused checks pass 58 tests in 2.00 s, including 512-cell projection/witness behavior, unplanned resolution rejection, previous-path release and failed-path exclusion for both audit entrypoints. Static checks pass. The machine currently has approximately 26 GiB available memory and 30 GiB swap; the earlier 512 audit used approximately 9 GiB peak RSS. Resource costs and any failure remain part of the record, and numerical work is not restarted just to repair reporting.

The [completed observation](planar-1024-refinement-20260920.md) retains the original screen: fourteen concrete groups fail, including renewed compression-damage failure. Independent physical verification, sparse runtime, broader topology/material/3D scope and release qualification remain open. Preserve failures and nonmonotone secondary maxima rather than assuming convergence from layer count alone.
