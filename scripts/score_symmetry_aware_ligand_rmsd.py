#!/usr/bin/env python3
"""Score ligand pose RMSD with explicit atom-symmetry permutations.

This scorer is intentionally chemistry-toolkit independent. The public
benchmark manifest supplies atom order and allowed symmetry permutations; the
scorer handles rigid alignment and selects the lowest RMSD across those
permutations.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "symmetry-aware-ligand-rmsd.v1"
DEFAULT_THRESHOLD_ANGSTROM = 2.0


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _coordinate_from_item(item: Any) -> tuple[float, float, float]:
    if isinstance(item, dict):
        return (float(item["x"]), float(item["y"]), float(item["z"]))
    if isinstance(item, (list, tuple)) and len(item) == 3:
        return (float(item[0]), float(item[1]), float(item[2]))
    raise ValueError("coordinate rows must be {'x','y','z'} objects or length-3 arrays")


def coordinates_array(items: Iterable[Any]) -> np.ndarray:
    coords = np.asarray([_coordinate_from_item(item) for item in items], dtype=np.float64)
    if coords.ndim != 2 or coords.shape[1] != 3:
        raise ValueError("coordinates must have shape (n_atoms, 3)")
    if coords.shape[0] == 0:
        raise ValueError("at least one atom coordinate is required")
    if not np.isfinite(coords).all():
        raise ValueError("coordinates must be finite")
    return coords


def kabsch_rmsd(reference: np.ndarray, predicted: np.ndarray) -> float:
    """Return centered, rigidly aligned RMSD for matching atom order."""
    if reference.shape != predicted.shape:
        raise ValueError("reference and predicted coordinates must have matching shape")
    ref_centered = reference - reference.mean(axis=0)
    pred_centered = predicted - predicted.mean(axis=0)
    covariance = pred_centered.T @ ref_centered
    left, _singular_values, right_t = np.linalg.svd(covariance)
    reflection_fix = np.eye(3)
    reflection_fix[2, 2] = np.sign(np.linalg.det(left @ right_t)) or 1.0
    rotation = left @ reflection_fix @ right_t
    aligned = pred_centered @ rotation
    squared_distance = np.sum((aligned - ref_centered) ** 2, axis=1)
    return float(np.sqrt(np.mean(squared_distance)))


def _normalized_permutations(
    permutations: Iterable[Iterable[int]] | None,
    atom_count: int,
) -> list[list[int]]:
    if permutations is None:
        return [list(range(atom_count))]
    rows = [list(row) for row in permutations]
    if not rows:
        return [list(range(atom_count))]
    expected = list(range(atom_count))
    normalized: list[list[int]] = []
    for row in rows:
        if sorted(row) != expected:
            raise ValueError("each symmetry permutation must contain every atom index exactly once")
        normalized.append(row)
    if expected not in normalized:
        normalized.insert(0, expected)
    return normalized


def score_symmetry_aware_rmsd(
    *,
    reference_atoms: Iterable[Any],
    predicted_atoms: Iterable[Any],
    symmetry_permutations: Iterable[Iterable[int]] | None = None,
    threshold_angstrom: float = DEFAULT_THRESHOLD_ANGSTROM,
) -> dict[str, Any]:
    reference = coordinates_array(reference_atoms)
    predicted = coordinates_array(predicted_atoms)
    if reference.shape != predicted.shape:
        raise ValueError("reference and predicted atom counts must match")
    permutations = _normalized_permutations(symmetry_permutations, reference.shape[0])
    rows: list[dict[str, Any]] = []
    for permutation in permutations:
        rmsd = kabsch_rmsd(reference, predicted[permutation, :])
        rows.append(
            {
                "permutation": permutation,
                "rmsd_angstrom": rmsd,
                "pass": bool(rmsd <= threshold_angstrom),
            }
        )
    best = min(rows, key=lambda row: float(row["rmsd_angstrom"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "atom_count": int(reference.shape[0]),
        "threshold_angstrom": float(threshold_angstrom),
        "symmetry_permutation_count": len(permutations),
        "best_rmsd_angstrom": float(best["rmsd_angstrom"]),
        "best_permutation": best["permutation"],
        "pose_success": bool(best["pass"]),
        "permutation_rows": rows,
        "claim_boundary": (
            "The scorer only evaluates rigid-alignment RMSD over manifest-supplied atom "
            "permutations. It does not infer chemical equivalence, protonation state, "
            "tautomer identity, or receptor preparation correctness."
        ),
    }


def score_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return score_symmetry_aware_rmsd(
        reference_atoms=payload.get("reference_atoms", []),
        predicted_atoms=payload.get("predicted_atoms", []),
        symmetry_permutations=payload.get("symmetry_permutations"),
        threshold_angstrom=float(
            payload.get("rmsd_threshold_angstrom", DEFAULT_THRESHOLD_ANGSTROM)
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fail-blocked", action="store_true")
    args = parser.parse_args(argv)

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    score = {
        **release_evidence_metadata(
            input_paths=[args.input],
            reused_evidence=False,
            reuse_policy="rmsd_recomputed_from_input_pose_coordinates",
        ),
        **score_payload(payload),
        "case_id": str(payload.get("case_id", "")),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(_json_text(score), encoding="utf-8")
    print(
        "symmetry-aware-ligand-rmsd: "
        f"{'PASS' if score['pose_success'] else 'BLOCKED'} "
        f"rmsd={score['best_rmsd_angstrom']:.6g}"
    )
    return 1 if args.fail_blocked and not score["pose_success"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
