# Engine v2 Result Quantity Contract

PR 6 introduces a typed, hashed SI quantity catalog for ResultIR comparison. It
does not replace the existing numerical, engineering or nonlinear ResultIR
authority envelopes; it gives those envelopes one versioned vocabulary for
units and tolerance evaluation.

The v1 catalog covers translation and rotation, force and moment reactions,
member force and moment, section force/moment/strain/curvature, and fiber
strain/stress. Every row fixes:

- canonical SI unit and component labels;
- the ResultIR authority axis that must already be established;
- positive absolute and relative tolerances;
- the `absolute_plus_relative_linf.v1` comparison rule.

For reference vector `r` and candidate vector `c`, the gate is:

```text
max(abs(c - r)) <= absolute_tolerance_si
                   + relative_tolerance * max(abs(r))
```

Tolerance success cannot create solver authority, promote an unsupported
quantity, or transfer authority from a fallback. Display-unit conversion also
cannot change authority. The catalog manifest is content-hashed and validated
against `result_quantity_catalog_v1.schema.json`; shape mismatch, non-finite
values, incomplete quantities, duplicate components and hash tampering fail
closed.

Primary implementation:

- `src/structural_analysis/engine_v2/contracts/result_quantity.py`
- `src/structural_analysis/schemas/result_quantity_catalog_v1.schema.json`
- `tests/test_result_quantity_catalog.py`

This contract alone does not make the corotational 2D frame public or
authoritative. PR 7 and PR 8 must bind the catalog to an exact compiler,
terminal receipt and engineering recovery path.
