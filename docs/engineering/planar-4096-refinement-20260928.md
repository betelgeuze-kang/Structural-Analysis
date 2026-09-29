# Complete 4,096-layer planar path and fixed 2,048/4,096 comparison

The frozen 4,096-layer source completed and committed all 40 displacement targets
from 2 to 80 mm. Its saved full path, index, 40 step files, checkpoint chain,
and reconstructed full JSON passed the bounded comparison reader. A separate
post-completion pass matched the size and SHA-256 of all 508 inventory entries.
The unchanged 2,048-layer feature packet was also verified against its pinned
inventory and receipt binding to the original path hashes; the original path
itself was checked when that packet was extracted. The comparison made no new
structural solve or training fit.

At the **original 1% exploratory group screen**, all 400 nodal/steel groups and
all 240 concrete groups pass for the 2,048/4,096 pair. The largest concrete
group difference is tensile damage, **0.506844% at 80 mm**, E3:gauss-0,
2,048-layer cell 1627. The largest nodal/steel difference is **0.000476148%**
(plastic and accumulated plastic strain, backstress, and dissipated energy
density at 24 mm). The original denominator, projection, material law, loads,
control DOF, tolerances, and 40-target history were not relaxed.

| Concrete field | Largest 2,048/4,096 group difference | Target |
| --- | ---: | ---: |
| Tensile history strain | 0.0104984% | 8 mm |
| Compressive history strain | 0.0084053% | 76 mm |
| Tensile damage | **0.5068440%** | 80 mm |
| Compressive damage | 0.1791733% | 22 mm |
| Dissipated energy density | 0.1172945% | 24 mm |
| Stress | 0.0530816% | 78 mm |

The earlier **1,024/2,048 pair still fails** its original tensile-damage group
at 74 mm by 1.08501989%. That historical result is not changed by the finer
pair. At the earlier target, the new 2,048/4,096 tensile-damage group difference
is 0.406431%, with its maximum at E1:gauss-0, cell 393. The prior
E3:gauss-2, 1,024-layer cell-269 neighborhood corresponds to 2,048-layer cells
538 and 539. At 74 mm, cell 538 and its two 4,096-layer children have zero
damage. Cell 539 has damage 0.0217003978, while its children have 0.0102328417
and 0.0329532975; their mean differs from cell 539 by 0.0001073282. The
E3:gauss-2 section's own maximum relative difference is 0.0107328%. These
accepted-fiber observations narrow the local onset question, but do not prove
a convergence order or continuum accuracy.

The frozen numerical source revision is
`3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`. The fine protocol SHA-256 is
`7f30057cd8b26b0706c96bf84d5fc81842c4dbfc319f8abfc5c618793d459881`.
The original 4,096-layer full JSON is **21,942,467,552 bytes**, SHA-256
`030122250b5b9b9013accdf86329d1cd6b98bfcf4bb74626bb71ef2bd1912e87`;
its index SHA-256 is
`f1c82345e9d4389a43d237a06e8c6eaecca9adc71cafc425eac74810858a5838`.
The 508-entry inventory SHA-256 is
`23bbd149afd4ed0c322239b4b313da5f99314f75af3135a52fc621e5b8c9c038`;
verified payloads total **42,522,738,508 bytes** because the full path and
individual steps are both retained. The separate comparison result SHA-256 is
`d8a81482c4b4bd5493b6879ff0b8245883f2dc7356613cc71381265443606678`.
The [machine summary](planar-4096-refinement-20260928.summary.json) preserves
all group maxima, hashes, run costs, and the prior onset neighborhood.

The numerical path took **9,061.451 s**; the enclosing interval through full
artifact hashing was **10,757.485 s**. These are nested scopes and must not be
added. They exclude later inventory verification and comparison. This larger
run is evidence of refinement under one fixed model/history, not a runtime
speedup or an independent physical validation.

The raw numerical packet is retained at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-4096-full-refinement-f_pu_uib`.
The independently generated composite comparison is retained at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-2048-4096-comparison-20260928/result.json`.
Neither multi-gigabyte original path nor the composite output is treated as a
new public solver result or training label. Physical validation against a
suitable experiment, other histories/geometries, and public-range authority
remain separate work.
