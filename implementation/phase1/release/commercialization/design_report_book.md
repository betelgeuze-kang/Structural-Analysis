# Design Report Book

- Generated at (UTC): `2026-04-19T13:44:40.899764+00:00`
- Summary: `Design report book: PASS | members=5 | checks=10 | max_dcr=1.240 | trace=100.0% | ng=4 | suggestions=5 | opt_changes=2 | sheet_diff=2`

## Summary

- Members: `5`
- Member checks: `10`
- Governing max DCR: `1.2400`
- Governing clause traceability: `100.0%`
- NG members: `4`
- Suggestions: `5`
- External sheet diff rows: `2`

## Governing Clause Table

| Clause | Members | NG | Max DCR | Governing Member |
|---|---:|---:|---:|---|
| KDS-RC-BEAM-FLEX-001 | 1 | 1 | 1.2400 | B1 |
| KDS-RC-SLAB-PUNCH-001 | 1 | 1 | 1.1800 | S1 |
| KDS-RC-WALL-BE-001 | 1 | 1 | 1.1200 | W1 |
| KDS-RC-CONN-SLIP-001 | 1 | 1 | 1.0800 | N1 |
| KDS-RC-BEAM-SHEAR-001 | 1 | 1 | 1.0500 | B1 |
| KDS-RC-COL-INT-001 | 1 | 0 | 0.5200 | C1 |

## NG Grouping

| Combination | Member Type | Clause | NG | Max DCR |
|---|---|---|---:|---:|
| RC_DETAIL | beam | KDS-RC-BEAM-FLEX-001 | 1 | 1.2400 |
| RC_DETAIL | slab | KDS-RC-SLAB-PUNCH-001 | 1 | 1.1800 |
| RC_DETAIL | wall | KDS-RC-WALL-BE-001 | 1 | 1.1200 |
| RC_DETAIL | connection | KDS-RC-CONN-SLIP-001 | 1 | 1.0800 |
| RC_DETAIL | beam | KDS-RC-BEAM-SHEAR-001 | 1 | 1.0500 |

## Member Family Envelope

| Member Type | Max DCR | Governing Clause | Governing Member |
|---|---:|---|---|
| beam | 1.2400 | KDS-RC-BEAM-FLEX-001 | B1 |
| slab | 1.1800 | KDS-RC-SLAB-PUNCH-001 | S1 |
| wall | 1.1200 | KDS-RC-WALL-BE-001 | W1 |
| connection | 1.0800 | KDS-RC-CONN-SLIP-001 | N1 |
| column | 0.5200 | KDS-RC-COL-INT-001 | C1 |

## Section Suggestions

| Member | Type | Direction | Action | Clause | Current DCR | Estimated After |
|---|---|---|---|---|---:|---:|
| B1 | beam | strengthen | beam_section_up | KDS-RC-BEAM-FLEX-001 | 1.2400 | 0.9500 |
| S1 | slab | strengthen | slab_thickness_up | KDS-RC-SLAB-PUNCH-001 | 1.1800 | 0.9500 |
| W1 | wall | strengthen | core_wall_up | KDS-RC-WALL-BE-001 | 1.1200 | 0.9500 |
| N1 | connection | strengthen | connection_detailing_up | KDS-RC-CONN-SLIP-001 | 1.0800 | 0.9500 |
| C1 | column | reduce | perimeter_frame_down | KDS-RC-COL-INT-001 | 0.5200 | 0.6500 |

## Optimization Linkage

| Member | Type | Action | Clause | Cost Delta | Max DCR |
|---|---|---|---|---:|---:|
| C1 | column | perimeter_frame_down | KDS-RC-COL-INT-001 | -42.0000 | 0.5200 |
| N1 | connection | connection_detailing_up | KDS-RC-CONN-SLIP-001 | 15.0000 | 1.0800 |

## External Sheet Diff

| Row Key | Changed Columns | Max Numeric Delta |
|---|---|---:|
| B1 | dcr,remark | 0.1800 |
