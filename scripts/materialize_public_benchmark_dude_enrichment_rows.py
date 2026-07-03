#!/usr/bin/env python3
"""Materialize DUD-E enrichment rows from official target SMILES files."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
from typing import Any

from rdkit import Chem
from rdkit.Chem import QED


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "public_benchmark_enrichment_rows.json"
DEFAULT_TARGET_ID = "AA2AR"
DEFAULT_TARGET_SLUG = "aa2ar"
DEFAULT_ACTIVE_LIMIT = 25
DEFAULT_DECOY_LIMIT = 250
SCHEMA_VERSION = "public-benchmark-dude-enrichment-rows.v1"
SCORE_METHOD = "rdkit_qed_baseline_label_independent"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _sha256_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _target_url(target_slug: str, filename: str) -> str:
    return f"https://dude.docking.org/targets/{target_slug}/{filename}"


def _target_page_url(target_slug: str) -> str:
    return f"https://dude.docking.org/targets/{target_slug}/"


def _read_source(*, path: Path | None, url: str, timeout: int) -> tuple[bytes, str]:
    if path is not None:
        return path.read_bytes(), path.as_posix()
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read(), url


def _parse_ism(text: str, *, role: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        smiles = parts[0]
        source_id = parts[-1] if len(parts) > 1 else f"{role}_{index}"
        rows.append(
            {
                "source_id": source_id,
                "source_row_number": str(index),
                "smiles": smiles,
                "smiles_sha256": _sha256_text(smiles),
            }
        )
    return rows


def _qed_score(smiles: str) -> float | None:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return round(float(QED.qed(mol)), 6)


def _scored_molecules(
    rows: list[dict[str, str]],
    *,
    target_id: str,
    role: str,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    molecules: list[dict[str, Any]] = []
    skipped_invalid = 0
    for row in rows:
        if len(molecules) >= limit:
            break
        score = _qed_score(row["smiles"])
        if score is None:
            skipped_invalid += 1
            continue
        source_row_number = int(row["source_row_number"])
        molecules.append(
            {
                "molecule_id": (
                    f"{target_id}_{role}_{source_row_number}_{row['source_id']}"
                ),
                "is_active": role == "active",
                "score": score,
                "score_method": SCORE_METHOD,
                "source_id": row["source_id"],
                "source_role": role,
                "source_row_number": source_row_number,
                "smiles_sha256": row["smiles_sha256"],
            }
        )
    return molecules, skipped_invalid


def build_dude_enrichment_rows(
    *,
    active_source: bytes,
    decoy_source: bytes,
    target_id: str = DEFAULT_TARGET_ID,
    target_slug: str = DEFAULT_TARGET_SLUG,
    active_limit: int = DEFAULT_ACTIVE_LIMIT,
    decoy_limit: int = DEFAULT_DECOY_LIMIT,
    active_ref: str | None = None,
    decoy_ref: str | None = None,
) -> dict[str, Any]:
    active_url = _target_url(target_slug, "actives_final.ism")
    decoy_url = _target_url(target_slug, "decoys_final.ism")
    active_rows = _parse_ism(active_source.decode("utf-8"), role="active")
    decoy_rows = _parse_ism(decoy_source.decode("utf-8"), role="decoy")
    active_molecules, invalid_active_count = _scored_molecules(
        active_rows,
        target_id=target_id,
        role="active",
        limit=active_limit,
    )
    decoy_molecules, invalid_decoy_count = _scored_molecules(
        decoy_rows,
        target_id=target_id,
        role="decoy",
        limit=decoy_limit,
    )
    combined_source = (
        active_url.encode("utf-8")
        + b"\n"
        + active_source
        + b"\n"
        + decoy_url.encode("utf-8")
        + b"\n"
        + decoy_source
    )
    source_checksum = _sha256_bytes(combined_source)
    target_page = _target_page_url(target_slug)
    return {
        "schema_version": SCHEMA_VERSION,
        "row_source": "DUD-E official target actives_final.ism and decoys_final.ism",
        "target_id": target_id,
        "target_slug": target_slug,
        "source_urls": {
            "target_page": target_page,
            "actives_final": active_url,
            "decoys_final": decoy_url,
        },
        "source_refs": {
            "actives_final": active_ref or active_url,
            "decoys_final": decoy_ref or decoy_url,
        },
        "source_checksums": {
            "actives_final": _sha256_bytes(active_source),
            "decoys_final": _sha256_bytes(decoy_source),
            "combined_source": source_checksum,
        },
        "selection_policy": {
            "active_limit": int(active_limit),
            "decoy_limit": int(decoy_limit),
            "ordering": "official_file_order",
            "invalid_smiles": "skipped_before_limit_counting",
        },
        "score_policy": {
            "score_method": SCORE_METHOD,
            "score_direction": "higher_is_better",
            "label_independent": True,
            "uses_active_decoy_label_for_score": False,
        },
        "targets": [
            {
                "benchmark_family": "DUD-E",
                "target_id": target_id,
                "score_direction": "higher_is_better",
                "source_license_or_accession": (
                    f"DUD-E:{target_id}:official_actives_final_and_decoys_final"
                ),
                "source_checksum": source_checksum,
                "provenance_ref": target_page,
                "score_method": SCORE_METHOD,
                "source_urls": {
                    "actives_final": active_url,
                    "decoys_final": decoy_url,
                },
                "source_row_counts": {
                    "actives_final": len(active_rows),
                    "decoys_final": len(decoy_rows),
                },
                "selected_row_counts": {
                    "active": len(active_molecules),
                    "decoy": len(decoy_molecules),
                },
                "invalid_smiles_counts": {
                    "active": invalid_active_count,
                    "decoy": invalid_decoy_count,
                },
                "selection_policy": {
                    "active_limit": int(active_limit),
                    "decoy_limit": int(decoy_limit),
                    "ordering": "official_file_order",
                },
                "scored_molecules": [*active_molecules, *decoy_molecules],
            }
        ],
        "claim_boundary": (
            "These rows use official DUD-E target SMILES and a deterministic RDKit "
            "QED baseline score. They close only the enrichment row-ingestion "
            "contract; they do not claim docking-engine enrichment, CASF/PDBBind "
            "pose success, or full Public Benchmark Phase 2 readiness."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-id", default=DEFAULT_TARGET_ID)
    parser.add_argument("--target-slug", default=DEFAULT_TARGET_SLUG)
    parser.add_argument("--active-limit", type=int, default=DEFAULT_ACTIVE_LIMIT)
    parser.add_argument("--decoy-limit", type=int, default=DEFAULT_DECOY_LIMIT)
    parser.add_argument("--actives-path", type=Path)
    parser.add_argument("--decoys-path", type=Path)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    active_url = _target_url(args.target_slug, "actives_final.ism")
    decoy_url = _target_url(args.target_slug, "decoys_final.ism")
    active_source, active_ref = _read_source(
        path=args.actives_path,
        url=active_url,
        timeout=args.timeout,
    )
    decoy_source, decoy_ref = _read_source(
        path=args.decoys_path,
        url=decoy_url,
        timeout=args.timeout,
    )
    payload = build_dude_enrichment_rows(
        active_source=active_source,
        decoy_source=decoy_source,
        target_id=args.target_id,
        target_slug=args.target_slug,
        active_limit=args.active_limit,
        decoy_limit=args.decoy_limit,
        active_ref=active_ref,
        decoy_ref=decoy_ref,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(_json_text(payload), encoding="utf-8")
    target = payload["targets"][0]
    selected = target["selected_row_counts"]
    print(
        "public-benchmark-dude-enrichment-rows: "
        f"{args.target_id} | active={selected['active']} | "
        f"decoy={selected['decoy']} | out={args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
