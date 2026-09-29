# Experimental fixed-displacement force-response floor

`scripts/audit_rc_force_response_floor.py` is a Python-only posthoc sidecar for
the existing pin/roller direct-control candidate packet. It applies a positive
lower bound to the **signed, dimensionless load factor at one exact authored
displacement target**. The load factor multiplies the model's fixed proportional
reference nodal loads; the sidecar records those loads and their kN unit. This
is a fixed-displacement force/stiffness response screen, not an ultimate strength,
design-code, or independent physical validation claim.
The baseline load factor at the chosen target must be positive, so this pilot
only screens response in the authored reference-load direction. It rejects a
reversal target with negative baseline load factor; an opposite-sign candidate
at an otherwise valid target fails the positive floor.

The plan has exactly these fields:

```json
{
  "schema_version": "experimental-rc-fixed-displacement-force-response-floor-plan.v1",
  "source_revision": "620492dc0ceefa6cee3257032277bf90c326ff43",
  "audit_receipt_sha256": "sha256:0f1fb706c9e2f5d6ffdbb87f5e80b2baadc7199cd4564653e096d6f3be5e1530",
  "target_index": 2,
  "target_displacement_m": -0.00014,
  "minimum_load_factor": 180.0,
  "evaluation_timing": "posthoc"
}
```

This example floor was chosen **after** the `620492dc0` oracle result was
observed. It is a diagnostic only. At target index 2, it classifies baseline,
`w42`, `w46`, and `w52` as passing, and `w34` and `w38` as failing. The original
v1 online plans, selected candidates, and exhaustive oracle result are unchanged.
Among the six saved oracle rows, `w42` has the cheapest synthetic estimate after
this posthoc floor filter; the original v1 oracle selected `w34`. The online
arms are not reevaluated by this sidecar and did not analyze `w42`.
The existing learned policy has no load-factor target and did not predict this
floor. The synthetic prices are authored arithmetic, not quotes or savings.

Given a plan JSON outside the packet, generate and independently rederive its
sidecar report with outputs in a new directory outside the packet:

```bash
PYTHONPATH=.:src python3 scripts/audit_rc_force_response_floor.py report \
  --packet /absolute/path/to/original-packet \
  --plan /absolute/path/to/floor-plan.json \
  --original-audit /absolute/path/to/original-audit.json \
  --output /absolute/path/to/new-report.json
PYTHONPATH=.:src python3 scripts/audit_rc_force_response_floor.py audit \
  --packet /absolute/path/to/original-packet \
  --plan /absolute/path/to/floor-plan.json \
  --original-audit /absolute/path/to/original-audit.json \
  --report /absolute/path/to/new-report.json \
  --output /absolute/path/to/new-audit.json
```

The sidecar requires a plan-pinned SHA-256 of a passing original packet audit
receipt, rehashes that audit's full packet inventory, and reads each oracle row's
original result and stored fresh-replay verification receipt. It checks the
accepted target index, displacement, step and checkpoint bindings before
deriving the load factor. Its audit mode rereads the originals and recomputes
the complete sidecar report. Receipt pinning and internal hashes establish
provenance within the supplied packet; they do **not** rerun the solver or
establish independent source or physical validity. This pilot requires every
oracle row to pass the original v1 screens; mixed-feasibility packets remain
unsupported.

A future prospective candidate study needs a separately versioned screen in
the train/search contract, a policy target for load factor if learned ranking
is to use it, and a floor plan committed and bound before any numerical run.
The present `posthoc` schema refuses a prospective timing claim.
