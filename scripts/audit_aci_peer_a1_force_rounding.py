"""Reproduce one fixed source-pair hypothesis; never convert or admit data."""

import argparse
import csv
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
import hashlib
import json
from pathlib import Path


ACI_SHA256 = "6b6e9df802f8d8cf13458ac454bf9129c0dab66c155564755f3f2dfd8dd2474e"
PEER_SHA256 = "49a5ae183c4bf70446fa09cf926cdd03393d72c86fc44dc80982b3c35e55c7a6"


def checked_bytes(path: Path, digest: str) -> bytes:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("original source SHA-256 mismatch")
    return raw


def audit(aci_path: Path, peer_path: Path) -> dict:
    aci_raw = checked_bytes(aci_path, ACI_SHA256)
    peer_raw = checked_bytes(peer_path, PEER_SHA256)
    aci = list(csv.reader(aci_raw.decode().splitlines()))
    if aci.pop(0) != ["Displacement (in.)", "Force(kips)"]:
        raise ValueError("unexpected ACI header")
    peer = [row.split() for row in peer_raw.decode().splitlines()[2:] if row.strip()]
    if len(aci) != 866 or len(peer) != 866:
        raise ValueError("expected complete 866-pair source histories")
    with localcontext() as context:
        context.prec = 60
        context.rounding = ROUND_HALF_EVEN
        residuals = []
        rounded_matches = 0
        displacement_matches = 0
        for original, other in zip(aci, peer, strict=True):
            force = Decimal(original[1])
            proposed = Decimal(other[1]) * Decimal("0.2248")
            quantum = Decimal(1).scaleb(force.as_tuple().exponent)
            residuals.append(abs(force - proposed))
            rounded_matches += proposed.quantize(quantum) == force
            displacement_matches += (
                Decimal(original[0]) * Decimal("25.4") == Decimal(other[0])
            )
    return {
        "schema": "aci-peer-a1-rounded-force-hypothesis.v1",
        "aci_source_sha256": ACI_SHA256,
        "peer_source_sha256": PEER_SHA256,
        "pair_count": len(aci),
        "ordered_displacement_matches": displacement_matches,
        "hypothesized_kn_to_kip_multiplier": "0.2248",
        "rounding": "ROUND_HALF_EVEN at each original ACI token exponent",
        "exact_force_matches": sum(value == 0 for value in residuals),
        "rounded_force_matches": rounded_matches,
        "maximum_absolute_force_difference_kip": str(max(residuals)),
        "exporter_rule_authenticated": False,
        "source_correction_applied": False,
        "training_admission_granted": False,
        "independent_physical_validation": False,
        "new_structural_solves": 0,
        "new_training_fits": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("aci_history", type=Path)
    parser.add_argument("peer_history", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.aci_history, args.peer_history), indent=2))
