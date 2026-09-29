# Committed force-floor price-search packet, 2026-09-29

The exact-source runner executed the committed
[`force-floor-prospective.protocol.json`](../../examples/research/rc_reuse_campaign/force-floor-prospective.protocol.json)
at protocol commit `2b470e675caae308b71ae9cd19ae776463c61938` from clean source
`255d8a6e6a7ca5f54633ef8d3130f8897e60930f`. The read-only independent
packet auditor returned `verified_packet_integrity`, no violations, and known
execution work. The 102 inventoried files total 9,462,458 bytes; the inventory
itself is an additional file. The packet is preserved locally
outside the repository at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/rc-force-floor-prospective-packet-20260929`.
The separate audit JSON is at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/rc-force-floor-prospective-audit-20260929.json`.

| Item | Observed value |
| --- | --- |
| Authored target | index 2, −0.00014 m |
| Positive signed load-factor floor | 180.0 |
| Price ordering | `w34`, `w38`, `w42`, `w46`, `w52` |
| Online shortlist, excluding baseline | `w34`, `w38`, `w42` |
| Online and complete-pool selections | `w42` and `w42` |
| Complete-pool verified minimum scoped estimate | 103.462524 invented KRW |
| Online selection minus pool minimum | 0.0 invented KRW |
| Full analysis and fresh replay invocations | 8 online + 12 oracle |
| Attempted steps, Newton iterations and linear solves | 80, 222 and 222, respectively |

Both arms completed their paths and fresh replays. At the authored target,
the baseline, `w34`, and `w38` had signed factors 176.226309, 154.889491,
and 169.114037, so they failed the floor. `w42`, `w46`, and `w52` had factors
183.338582, 197.563127, and 218.899945, so they passed. In the declared
pool, `w42` was the cheapest verified candidate passing every upper and lower
screen. The online arm analyzed it before the separate full-pool oracle.

The earlier v1 packet selected `w34` under upper-only limits, but its baseline
width was 0.44 m, while this committed protocol's baseline is 0.40 m. The five
alternative widths, control request, experiment screens and synthetic prices
have matching JSON values. The current packet demonstrates the implemented
lower-bound decision, not a controlled timing comparison with that old run.
The 180.0 floor was chosen after the earlier packet was examined. No learned
ranking was used, and this run supplies no held-out AI, independent physical,
market-price, or engineering approval evidence.

Reproducibility identifiers: protocol SHA-256
`e28172956b3404b19eb53cc10daea6c89f07f7fc3c4f12d59bd2c090414ee783`,
search report hash
`sha256:4bcc52e7dc43e600ef83a2dd64e5f135f2022a49a450f8c9469fc75039d3e8c3`,
packet inventory file SHA-256
`ece0db24cd88e976e2764f2d26f3e38890aedf9d9b5095cf9cf7751e6210dc2f`,
and independent audit JSON SHA-256
`b6ee6a272235c4bfc187988ba1fadf1ab04e9ad6d9313702f41dfc6a195cbcfc`.
