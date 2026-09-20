# Measured original-campaign audit cost

The committed auditor at `2588eeefa5b85c0e2b72dcacb5585d7da27d4106` ran in three fresh Python processes against the preserved 128-path campaign. The source was archived before execution. No solver was rerun and no policy was trained or promoted.

| Repeat | Enclosing process seconds | Child user seconds | Child system seconds |
| --- | ---: | ---: | ---: |
| 1 | 11.914744106 | 11.653735 | 0.259840 |
| 2 | 12.015187670 | 11.775102 | 0.235871 |
| 3 | 12.129163167 | 11.831928 | 0.295784 |

All three audit outputs match exactly. The original 3,492 JSON files (233,927,075 bytes) were hashed before and after and remained unchanged. Each output retains 128 paths, 70 complete, 802 native calls and 4,702 Newton iterations/linear solves; the 58 incomplete paths remain incomplete.

The timed boundary includes interpreter startup, imports, reading/parsing, hash and history/work validation, result serialization and process exit. It excludes source archiving, the separate before/after inventory, browser rendering, transport and numerical execution. Filesystem caches were not flushed; the initial inventory reads warm data, so these are ordinary cached-read observations, not cold-start benchmarks. The three repeats are one host and one campaign, not independent physical cases or concurrent-load controls.

Original campaign enclosing numerical process time was 115.470117122 seconds at source `84714992a`. That earlier measurement is not a paired timing control for this audit. It must not be added to these observations and presented as a measured complete user-flow time or speedup. The new evidence establishes a separately measurable validation cost of roughly 12 seconds in this workload. Complete preparation/transport/browser review costs remain open, as do independent physics and learned benefit.

## Retained evidence

Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-audit-cost-hcshmvnm`. The packet preserves the driver, archived source, three full outputs/stdout/stderr pairs, original JSON inventory and measured timings. All 724 full-inventory entries were reread and verified. Full-inventory SHA-256: `cc406aeb8be40b38e97ebbd1bcba455183f6ecf758a19f848c51baa0a2471634`.

Machine-readable observations: [summary](rc-adaptive-audit-cost-20260921.summary.json). This timing study does not change code behavior; the previously recorded forty focused tests are not presented as a new run.
