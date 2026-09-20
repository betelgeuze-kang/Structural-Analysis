# Full 1,024-layer observation: local material convergence remains open

The fixed forty-target experiment completes all forty accepted steps and passes its internal solver contract. The original 512/1,024 comparison passes all 400 nodal/steel groups, but **14 of 240 concrete groups fail the unchanged exploratory 1% screen**. Thirteen failures concern tensile damage; compression damage fails at 22 mm.

| Concrete field | Maximum relative group difference | Target | Witness |
| --- | ---: | ---: | --- |
| Tensile history strain | 0.041449% | 4 mm | E1, Gauss 0, coarse cell 221 |
| Compressive history strain | 0.030711% | 56 mm | E3, Gauss 2, coarse cell 103 |
| Tensile damage | 2.147216% | 78 mm | E3, Gauss 2, coarse cell 132 |
| Compressive damage | 1.201425% | 22 mm | E2, Gauss 0, coarse cell 7 |
| Dissipated energy density | 0.383075% | 22 mm | E2, Gauss 0, coarse cell 7 |
| Stress | 0.224526% | 78 mm | E3, Gauss 2, coarse cell 132 |

The count improves from 70 → 34 → 27 → 14 over successive 64/128, 128/256, 256/512 and 512/1,024 comparisons. That does not prove uniform convergence: compression damage rises from the previous 0.856133% maximum to 1.201425%, and its witness changes. Tensile failures occur at 46 mm and every 2 mm target from 58 through 80 mm. No group or target is excluded from the denominator.

## Source and cost

The numerical engine remains `3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`; the driver/comparison snapshot is `4d47f89ee670c7a3153fa3129218cd237b6f365d`. The [predeclared protocol](planar-1024-refinement-protocol-20260920.md) fixes the original model, materials, tolerances, forty targets, DOF 15 and proportional force vector. This is not constant axial loading.

- Numerical setup: 0.596245 s; full path: **2305.985865 s**; through output hashing: 2465.344714 s. These intervals are nested, not additive.
- Enclosing numerical process: 2472.637152 s, exit 0, maximum child RSS 25,006,308 KiB.
- Original numerical packet: 466 files, 5,517,595,286 bytes. All payload hashes verify; inventory SHA-256 `73fdebb2170c4ea49bc9a5a73c1645cb2a6247b4af8af2242067441320415307`.
- Result SHA-256: `2f923d7537b4ddf10ce19e0959fd081767466442e9f438ef1265c7461154446b`.
- Subsequent payload and 955-file frozen observer-source verification: 2.898508 s. Read-only comparison: 117.821149 s, exit 0, maximum RSS 17,879,132 KiB, zero swaps reported.

The controller failed **after** the numerical child succeeded: its verification code used `hashlib.file_digest`, unavailable in Python 3.10. The original packet and controller were preserved. A separate recovery launcher used chunked SHA-256 reads, verified the files and frozen comparison sources, and executed only the planned read-only comparison. No numerical solve or training fit was repeated. The failed controller verification interval was not separately timed; no complete enclosing recovery-cost total is claimed.

Recovery/audit packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-512-1024-audit-s7ze8hxd`. Its seven payload files (1,049,283 bytes) verify against inventory SHA-256 `af37666e6364c48a514af49bc91177349c80daf475cffe88afb55ba1768607ad`. The [machine-readable summary](planar-1024-refinement-20260920.summary.json) binds the numerical packet, recovery, costs, maxima and failed targets.

## Implication for the roadmap

This is one internal numerical experiment, not physical validation, sparse-runtime qualification or public API expansion. Retain the original local screen and investigate the renewed 22 mm compression discrepancy as well as tensile onset sampling. Do not infer a passing 2,048-layer outcome from decreasing failure counts. The current numerical process already peaks near 24 GiB RSS; another whole-path refinement needs an explicit storage/memory strategy before execution. All independent physical, licensing and broader material/3D requirements remain open.
