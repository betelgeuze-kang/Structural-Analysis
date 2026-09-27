# Pinned 2,048-layer coarse features for a future 4,096-layer comparison

The retained 2,048-layer full nonlinear path was read with
`scripts/extract_planar_2048_features.py` on 2026-09-27. The extractor checked
the frozen protocol, indexed full-file bytes, all 40 accepted steps, their
checkpoint chain and the reconstructed original full JSON before writing a
separate feature packet. It performed no structural solve or training fit.

| Pinned object | SHA-256 | Bytes |
| --- | --- | ---: |
| Original full path | `434faa33ae5360b332897d3e0c7171844a95182630082d9f9689a885d7ff71f6` | 10,986,493,493 |
| Original path index | `e1fabd392c7a32648cac7afd610483940fff467cdcf0413bce2e1a057a66878d` | 6,599 |
| Original protocol | `6508da674654590141a1b4084b9f59069a70db834da8c4070be153f0dccf9e43` | 1,839 |
| Extracted `features.json` | `8faae14f83d9cb837139570c54071984a9b5795568cca3044b0f8b5090890c3d` | 487,667,800 |
| Extracted `result.json` | `0c4e8fc952dfc9dc7048ddc033c0c947376dd7b0f9b0c903ff0ef4c5e969c38c` | 595 |
| Extracted `inventory.json` | `2a4b667df986d9e50460be6f6ef786318983cc95db691a28dd665e1280a1a03a` | 383 |

The source root was
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-2048-full-refinement-e9q90_me`.
The new packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-2048-comparison-features-20260927`.
The packet contains only the three listed files. Independently re-reading it
through `audit_planar_4096_refinement.coarse_features` verified the inventory,
receipt and feature hashes, source revision `3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`,
and all 40 targets from 0.002 through 0.080 m.

Reproduction command from the repository root:

```bash
PYTHONPATH=.:src python3 scripts/extract_planar_2048_features.py \
  /mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-2048-full-refinement-e9q90_me \
  /mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-2048-comparison-features-20260927
```

The last path must be new because the extractor creates it exclusively. The
feature packet is a verified coarse input, not a 2,048/4,096 numerical
comparison. No accepted 4,096-layer path or new 1% screen result exists yet.
The earlier 1,024/2,048 concrete tensile-damage screen still fails at
1.08501989%; neither that screen nor its denominator was changed.
