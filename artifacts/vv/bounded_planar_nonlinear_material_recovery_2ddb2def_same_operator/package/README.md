# Bounded planar nonlinear/material/recovery execution package

This package binds six exact current-product references and one standalone
OpenSees runner. The cases cover a gravity-prestressed P-Delta portal, the
elastic Lee-frame first limit point and post-limit branch, monotonic steel
yielding, one nonlinear RC fiber-section state, elastic section-resultant
recovery, and elastic per-fiber strain/stress recovery.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python runner/run_case.py --case-id bounded_planar_p_delta --model models/bounded_planar_p_delta.case.json --out external-results/bounded_planar_p_delta.json
.venv/bin/python runner/run_case.py --case-id bounded_planar_snap_through --model models/bounded_planar_snap_through.case.json --out external-results/bounded_planar_snap_through.json
.venv/bin/python runner/run_case.py --case-id bounded_planar_steel_yield --model models/bounded_planar_steel_yield.case.json --out external-results/bounded_planar_steel_yield.json
.venv/bin/python runner/run_case.py --case-id bounded_planar_rc_fiber --model models/bounded_planar_rc_fiber.case.json --out external-results/bounded_planar_rc_fiber.json
.venv/bin/python runner/run_case.py --case-id bounded_planar_section_recovery --model models/bounded_planar_section_recovery.case.json --out external-results/bounded_planar_section_recovery.json
.venv/bin/python runner/run_case.py --case-id bounded_planar_fiber_recovery --model models/bounded_planar_fiber_recovery.case.json --out external-results/bounded_planar_fiber_recovery.json
```

Return all six self-hashed JSON results with this unchanged package and the
operator provenance. The prepared package alone grants no V&V matrix credit,
Verification Level 2, design authority, commercial equivalence, or release
authority.
