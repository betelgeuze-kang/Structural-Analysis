# Full-size stepwise artifact round trip

The [stepwise writer](planar-path-storage-protocol-20260920.md) has reproduced the retained 1,024-layer full-result bytes exactly. Both original and rewritten SHA-256 are `2f923d7537b4ddf10ce19e0959fd081767466442e9f438ef1265c7461154446b`. All forty strict-decoded step copies equal the corresponding original step objects. Metadata also equals the original ordered metadata with the empty steps placeholder.

Observer source is `25b6a52d33f0c13a8043529f8364abbd2a55cec1`. This execution reads the already completed numerical artifact; it performs no structural solve or training fit and does not alter the original packet. The fourteen concrete comparison failures remain unchanged.

| Measured interval | Seconds |
| --- | ---: |
| Full original load and digest verification | 70.294880 |
| Stepwise output and hashing | 260.227123 |
| Metadata/forty step-copy verification | 71.414121 |
| Enclosing child process | 405.654611 |

The enclosing time includes those stages, not an additional cost to add to them. Source snapshot creation and final packet inventory writing are outside it. Maximum child RSS is 17,671,728 KiB. Because this test first loads the full original JSON, it does not measure a bounded-reader memory benefit or the numerical driver's peak after storage changes. No speedup is claimed. Duplicated full and per-step data deliberately increase disk use.

Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-1024-artifact-roundtrip-75uzdg9r`. All **812 files / 10,688,372,335 bytes** verify against inventory SHA-256 `3c4fec31d151d40725da3b87da6f38e13b476fea0e0562df2ca4a57abb4cdf6a`. The indexed artifact root is its `rewritten` directory; index SHA-256 is `effa668ba984929d1e8e0410146eef39dff438e359a44f6a49b7c4a8749dfbe5`.

The [machine-readable summary](planar-path-roundtrip-20260920.summary.json) retains exact hashes, times and counts. The next observation applies the bounded reader to this proven byte-equivalent packet, validates every accepted step and material binding, and records actual memory and cost. Higher-resolution numerical work has not begun.
