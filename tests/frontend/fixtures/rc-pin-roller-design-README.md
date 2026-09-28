# Synthetic pin/roller design comparison fixture

`rc-pin-roller-design-artifacts.json.gz` contains the original JSON bytes from
`compare_rc_control_designs` at backend commit `7b472c1b7246bef8821ce6351fa1d8432ff728ab`.
It uses `examples/research/rc_reuse_campaign/pin-roller-steel-plastic.model.json`,
a v4 request controlling global DOF 10 at `-1e-6` and `-2e-6` m, and
a single `RC1` width change from 0.4 to 0.5 m. The common prices are synthetic:
100 KRW/m³ gross concrete and 1 KRW/kg straight longitudinal rebar.
The report's `source_revision` is a caller-declared `a` × 40 placeholder and
explicitly is not a source attestation.

The archive stores `comparison.json` and each referenced candidate artifact
as base64 strings. The frontend tests check the producer's existing byte hashes,
stored full-path replay receipts, quantities, and selection. This is a browser
integrity fixture, not independent physical validation or a real cost quote.
