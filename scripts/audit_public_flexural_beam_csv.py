"""Inspect the pinned original Zenodo 8062007 table, without training admission."""

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path

CSV_SHA256 = "a37641e015c0e7052e9450d5530935594a3a13cbfb83296952e4bc0bd06aa8a9"


def inspect(raw):
    if hashlib.sha256(raw).hexdigest() != CSV_SHA256:
        raise ValueError("original CSV hash mismatch")
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    header = [h.strip() for h in rows[0]]
    named = [i for i, name in enumerate(header) if name]
    if len({header[i] for i in named}) != len(named):
        raise ValueError("ambiguous named columns")
    records = []
    blank = 0
    for row in rows[1:]:
        if len(row) != len(header):
            raise ValueError("row width mismatch")
        if any(value.strip() for i, value in enumerate(row) if not header[i]):
            raise ValueError("unlabeled nonempty values")
        if not any(value.strip() for value in row):
            blank += 1
            continue
        records.append({header[i]: row[i].strip() for i in named})
    ids = [r["No."] for r in records]
    if ids != [str(i) for i in range(1, 805)]:
        raise ValueError("original specimen sequence changed")
    controls = [r for r in records if r["Corrosion Method"] == "C"]

    def group(row):
        return row["Author, Specimen ID"].split(",", 1)[0].strip()

    endpoints = [
        "Py (kN)",
        "Pmax (kN)",
        "Mmax,exp (kNm)",
        "Δy (mm)",
        "Δult (mm)",
        "Elastic Stiffness, k (kN/mm)",
        "Displacement Ductility, μΔ",
    ]
    return {
        "schema": "zenodo-8062007-original-table-inspection.v1",
        "csv_sha256": CSV_SHA256,
        "raw_column_count": len(header),
        "named_column_count": len(named),
        "empty_unnamed_columns": len(header) - len(named),
        "specimen_rows": len(records),
        "blank_rows": blank,
        "author_reference_prefix_count": len({group(r) for r in records}),
        "duplicate_author_specimen_labels": {
            k: v
            for k, v in Counter(r["Author, Specimen ID"] for r in records).items()
            if v > 1
        },
        "explicit_control_code_rows": len(controls),
        "control_reference_prefix_count": len({group(r) for r in controls}),
        "control_configuration_counts": dict(
            sorted(Counter(r["Test Type and Configuration"] for r in controls).items())
        ),
        "control_compression_test_method_counts": dict(
            sorted(Counter(r["Comp. Test Method"] for r in controls).items())
        ),
        "control_endpoint_nonblank_counts": {
            key: sum(bool(r[key]) for r in controls) for key in endpoints
        },
        "control_source_groups": dict(
            sorted(Counter(group(r) for r in controls).items())
        ),
        "named_columns": [header[i] for i in named],
        "grouping_boundary": "Reference prefixes are source-discovery labels, not proof of independent projects or absence of reused specimens. Preserve specimen IDs and inspect original publications before split assignment.",
        "response_boundary": "Table contains scalar endpoints, not ordered load-displacement or material strain histories. Nonblank counts are availability screens, not validation of numerical meaning.",
        "training_rows_admitted": 0,
        "fits": 0,
        "structural_solves": 0,
        "independent_physical_validation": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = inspect(args.csv.read_bytes())
    with args.output.open("x") as f:
        f.write(
            json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        )
