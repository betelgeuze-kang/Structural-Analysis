# Two post-hoc witnesses of the 512/1,024 material difference

The completed [full comparison](planar-1024-refinement-20260920.md) leaves fourteen concrete groups outside the original screen. This diagnostic selects its maximum compression-damage witness (E2/Gauss 0/cell 7 at 22 mm) and maximum tensile-damage witness (E3/Gauss 2/cell 132 at 78 mm). Selection occurs after observing those maxima; this is not independent evaluation or an all-point claim.

The frozen original material law is replayed through all forty accepted section-strain targets at each coarse midpoint. Every coarse material state and stress exactly reproduces its stored accepted counterpart (80 point-target checks). The finer section history is also replayed at that same coordinate. Its response is derived, not an accepted finer solver fiber. The two original finer child values remain separately retained.

Let C be the coarse accepted value, M the derived finer-history response at the same midpoint, and L/R the accepted finer child values. The signed decomposition is `C - (L+R)/2 = (C-M) + (M-(L+R)/2)`. Signs are retained even when the terms oppose one another; the identity is algebraic, not causal attribution.

| Witness field | C | M | L | R |
| --- | ---: | ---: | ---: | ---: |
| Compression damage, 22 mm | 0 | 0 | 0.000796424314 | 0 |
| Tensile damage, 78 mm | 0.004749499622 | 0.004903313638 | 0 | 0.052443319630 |

For compression, the entire signed difference of -0.000398212157 belongs to the sampling term; the same-coordinate history term is zero. For tension, the signed history term is -0.000153814016 and the signed sampling term -0.021318346177. The latter is 99.283658% of their signed total. These are the selected local witnesses, not percentages of global error or physical damage. Both contain a child where damage has not started and a child where it has.

This supports further examination of integration-point placement and damage onset before simply interpreting higher layer count as uniform convergence. It does not replace the original fourteen failures, alter the 1% screen, establish a continuum solution or validate the material law experimentally.

## Reproducibility and costs

- Numerical/material source remains `3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`; observer source is `e424051da`.
- The observer verifies both full-result hashes, each accepted path and selected section/fiber bindings. It releases each large path after extracting compact histories before reading the next path.
- Focused checks: 74 pass in 2.19 s, including reversal-history replay, altered-state rejection, signed cancellation and existing reader/diagnostic contracts; Ruff and diff checks pass.
- This execution performs **160 material integrations, zero structural solves and zero training fits**. Outer observer wall time is 109.633794 s; maximum RSS is 17,672,176 KiB. Snapshot creation and final inventory writing are outside that timer.
- Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-1024-witness-977sn6jf`. All 768 payload files / 16,498,068 bytes verify. Inventory SHA-256: `1b771d68ae412c77c177d74c93477f3b64653ecb9240ae55e67aac880928a4df`.
- The [summary](planar-1024-witnesses-20260920.summary.json) retains exact witness values, source hashes and boundaries. The packet retains every target and field, not just the selected maxima.
