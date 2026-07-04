#!/usr/bin/env python3
"""Run Vina/GNINA bundle commands and complete engine-run receipts."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shlex
import subprocess
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_ENGINE_RUN_BUNDLE = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_engine_run_bundle.json"
)
DEFAULT_INPUT_MANIFEST = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_input_manifest.csv"
)
DEFAULT_OUT_REPORT = (
    PRODUCTIZATION
    / "public_benchmark_vina_gnina_engine_run_receipts_completion_report.json"
)
SCHEMA_VERSION = "public-benchmark-vina-gnina-engine-run-receipts-completion.v1"
DEFAULT_RMSD_THRESHOLD_ANGSTROM = 2.0


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    if not resolved.is_file():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(repo_root: Path, path: Path, payload: dict[str, Any]) -> None:
    resolved = _resolve(repo_root, path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _required_text(value: Any) -> str:
    return str(value or "").strip()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_manifest(repo_root: Path, path: Path) -> dict[str, dict[str, str]]:
    resolved = _resolve(repo_root, path)
    with resolved.open("r", encoding="utf-8", newline="") as handle:
        return {
            str(row.get("case_id") or "").strip(): {
                str(key): str(value or "").strip()
                for key, value in row.items()
                if key is not None
            }
            for row in csv.DictReader(handle)
        }


def _first_float(text: str, patterns: list[str]) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        if math.isfinite(value):
            return value
    return None


def _sdf_molecules(path: Path) -> list[Any]:
    from rdkit import Chem

    supplier = Chem.SDMolSupplier(str(path), sanitize=False, removeHs=False)
    return [mol for mol in supplier if mol is not None]


def _sanitize_heavy_mol(mol: Any) -> Any:
    from rdkit import Chem

    Chem.SanitizeMol(mol)
    heavy = Chem.RemoveHs(mol, sanitize=False)
    Chem.SanitizeMol(heavy)
    return heavy


def _score_from_pose_sdf(path: Path, engine_id: str) -> tuple[float | None, str]:
    molecules = _sdf_molecules(path)
    if not molecules:
        return None, "pose_sdf_molecules_missing"
    first = molecules[0]
    if engine_id == "vina" and first.HasProp("meeko"):
        try:
            meeko_payload = json.loads(first.GetProp("meeko"))
            score = float(meeko_payload.get("free_energy"))
        except (TypeError, ValueError, json.JSONDecodeError):
            score = math.nan
        if math.isfinite(score):
            return score, "sdf_property:meeko.free_energy"
    if first.HasProp("minimizedAffinity"):
        try:
            score = float(first.GetProp("minimizedAffinity"))
        except ValueError:
            score = math.nan
        if math.isfinite(score):
            return score, "sdf_property:minimizedAffinity"
    if first.HasProp("CNNaffinity"):
        try:
            score = float(first.GetProp("CNNaffinity"))
        except ValueError:
            score = math.nan
        if math.isfinite(score):
            return score, "sdf_property:CNNaffinity"
    return None, "pose_sdf_score_property_missing"


def _score_from_output(stdout: str, stderr: str) -> tuple[float | None, str]:
    text = f"{stdout}\n{stderr}"
    score = _first_float(
        text,
        [
            r"^\s*1\s+(-?\d+(?:\.\d+)?)\s+[-+]?\d",
            r"affinity\s*[:=]\s*(-?\d+(?:\.\d+)?)",
            r"free_energy\s*[:=]\s*(-?\d+(?:\.\d+)?)",
        ],
    )
    return (score, "engine_output:first_mode_affinity") if score is not None else (None, "")


def _engine_version_from_output(
    engine_id: str,
    current_version: str,
    stdout: str,
    stderr: str,
) -> str:
    text = f"{stdout}\n{stderr}"
    if engine_id == "gnina":
        match = re.search(r"(gnina\s+v[^\n]+)", text, flags=re.IGNORECASE)
        if match:
            return " ".join(match.group(1).split())
    if engine_id == "vina":
        match = re.search(r"(\d+\.\d+(?:\.\d+)?)", current_version)
        if match:
            return f"vina-python-api {match.group(1)}"
    return current_version


def _query_free_reference_path(
    repo_root: Path,
    manifest_row: dict[str, str],
    bundle_row: dict[str, Any],
) -> Path:
    prepared_ligand = Path(
        _required_text(
            bundle_row.get("prepared_ligand_path")
            or manifest_row.get("prepared_ligand_path")
        )
    )
    if prepared_ligand.name.endswith("_ligand.pdbqt"):
        candidate = prepared_ligand.with_name(
            prepared_ligand.name.replace("_ligand.pdbqt", "_ligand_query_free.sdf")
        )
        if _resolve(repo_root, candidate).is_file():
            return candidate
    return Path(_required_text(manifest_row.get("reference_ligand_path")))


def _heavy_atom_symmetry_rmsd(reference_sdf: Path, predicted_sdf: Path) -> tuple[float, str]:
    from rdkit import Chem
    from rdkit.Chem import rdFMCS, rdMolAlign

    reference_molecules = _sdf_molecules(reference_sdf)
    predicted_molecules = _sdf_molecules(predicted_sdf)
    if not reference_molecules:
        raise ValueError("reference_sdf_molecules_missing")
    if not predicted_molecules:
        raise ValueError("predicted_sdf_molecules_missing")
    try:
        reference = _sanitize_heavy_mol(reference_molecules[0])
        predicted = _sanitize_heavy_mol(predicted_molecules[0])
        return (
            float(rdMolAlign.GetBestRMS(reference, predicted)),
            "RDKit rdMolAlign.GetBestRMS on sanitized heavy atoms for the first predicted SDF pose",
        )
    except Exception:
        reference = Chem.RemoveHs(reference_molecules[0], sanitize=False)
        predicted = Chem.RemoveHs(predicted_molecules[0], sanitize=False)
        mcs = rdFMCS.FindMCS(
            [reference, predicted],
            atomCompare=rdFMCS.AtomCompare.CompareElements,
            bondCompare=rdFMCS.BondCompare.CompareAny,
            timeout=10,
        )
        if not mcs.smartsString or mcs.numAtoms != reference.GetNumAtoms():
            raise ValueError("heavy_atom_mcs_mapping_incomplete")
        pattern = Chem.MolFromSmarts(mcs.smartsString)
        reference_match = reference.GetSubstructMatch(pattern)
        predicted_match = predicted.GetSubstructMatch(pattern)
        if (
            len(reference_match) != reference.GetNumAtoms()
            or len(predicted_match) != predicted.GetNumAtoms()
        ):
            raise ValueError("heavy_atom_mcs_match_incomplete")
        atom_map = list(zip(predicted_match, reference_match))
        return (
            float(rdMolAlign.AlignMol(predicted, reference, atomMap=atom_map)),
            "RDKit MCS heavy-atom AlignMol fallback for unsanitized first predicted SDF pose",
        )


def _command_argv(repo_root: Path, command: str) -> list[str]:
    return shlex.split(command.replace("$PWD", str(repo_root)))


def _run_bundle_row(
    *,
    repo_root: Path,
    bundle_row: dict[str, Any],
    manifest_rows: dict[str, dict[str, str]],
    timeout_seconds: int,
    force: bool,
    reuse_existing_poses: bool,
) -> dict[str, Any]:
    case_id = _required_text(bundle_row.get("case_id"))
    engine_id = _required_text(bundle_row.get("engine_id"))
    run_key = f"{case_id}::{engine_id}"
    receipt_ref = Path(_required_text(bundle_row.get("receipt_template_ref")))
    receipt = _load_json(repo_root, receipt_ref)
    existing_status = _required_text(receipt.get("status")).lower()
    pose_ref = Path(
        _required_text(
            receipt.get("predicted_ligand_path_or_pose_ref")
            or bundle_row.get("predicted_ligand_path_or_pose_ref")
        )
    )
    pose_path = _resolve(repo_root, pose_ref)
    if (
        not force
        and existing_status in {"complete", "completed", "engine_run_complete", "ready"}
        and pose_path.is_file()
        and _required_text(receipt.get("predicted_ligand_checksum"))
    ):
        return {
            "run_key": run_key,
            "status": "skipped_complete",
            "receipt_ref": str(receipt_ref),
            "pose_ref": str(pose_ref),
            "blockers": [],
        }
    pose_path.parent.mkdir(parents=True, exist_ok=True)
    command = _required_text(bundle_row.get("command") or receipt.get("command"))
    blockers: list[str] = []
    reused_existing_pose = bool(reuse_existing_poses and pose_path.is_file())
    if reused_existing_pose:
        returncode = int(receipt.get("returncode") or 0)
        stdout = _required_text(receipt.get("stdout_tail"))
        stderr = _required_text(receipt.get("stderr_tail"))
    else:
        completed = subprocess.run(
            _command_argv(repo_root, command),
            check=False,
            cwd=repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
        returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    if returncode != 0:
        blockers.append("engine_command_failed")
    if not pose_path.is_file():
        blockers.append("predicted_ligand_file_missing")

    pose_checksum = _sha256_file(pose_path) if pose_path.is_file() else ""
    score, score_source = (
        _score_from_pose_sdf(pose_path, engine_id) if pose_path.is_file() else (None, "")
    )
    if score is None:
        score, score_source = _score_from_output(stdout, stderr)
    if score is None:
        blockers.append("score_unavailable")

    manifest_row = manifest_rows.get(case_id, {})
    rmsd: float | None = None
    rmsd_method = ""
    reference_ref = _query_free_reference_path(repo_root, manifest_row, bundle_row)
    try:
        rmsd, rmsd_method = _heavy_atom_symmetry_rmsd(
            _resolve(repo_root, reference_ref), pose_path
        )
    except Exception as exc:
        blockers.append(f"symmetry_aware_rmsd_failed:{exc.__class__.__name__}")

    config_ref = Path(_required_text(bundle_row.get("config_ref")))
    config_payload = _load_json(repo_root, config_ref)
    actual_config_checksum = _sha256_text(_json_text(config_payload)) if config_payload else ""
    expected_config_checksum = _required_text(
        receipt.get("engine_config_checksum") or bundle_row.get("config_checksum")
    )
    engine_version = _engine_version_from_output(
        engine_id,
        _required_text(receipt.get("engine_version")),
        stdout,
        stderr,
    )
    if actual_config_checksum and expected_config_checksum != actual_config_checksum:
        blockers.append("engine_config_checksum_mismatch")

    status = "engine_run_complete" if not blockers else "engine_run_blocked"
    updated_receipt = {
        **receipt,
        "status": status,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "returncode": returncode,
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
        "pose_execution_source": (
            "existing_pose_artifact" if reused_existing_pose else "engine_command"
        ),
        "predicted_ligand_path_or_pose_ref": str(pose_ref),
        "predicted_ligand_checksum": pose_checksum,
        "engine_version": engine_version,
        "engine_config_checksum": expected_config_checksum,
        "symmetry_aware_rmsd_angstrom": rmsd if rmsd is not None else "",
        "pose_success": bool(rmsd <= DEFAULT_RMSD_THRESHOLD_ANGSTROM)
        if rmsd is not None
        else "",
        "score": score if score is not None else "",
        "score_direction": _required_text(
            receipt.get("score_direction") or "lower_is_better"
        ),
        "score_source": score_source,
        "rmsd_method": rmsd_method,
        "rmsd_reference_ligand_path": str(reference_ref),
        "rmsd_threshold_angstrom": DEFAULT_RMSD_THRESHOLD_ANGSTROM,
        "claim_boundary": (
            "This receipt records a locally executed Vina/GNINA command, pose "
            "artifact checksum, first-pose score, and heavy-atom symmetry-aware "
            "RMSD. It does not independently validate receptor preparation, "
            "protonation, or benchmark licensing beyond the referenced source "
            "artifacts."
        ),
    }
    _write_json(repo_root, receipt_ref, updated_receipt)
    return {
        "run_key": run_key,
        "status": status,
        "receipt_ref": str(receipt_ref),
        "pose_ref": str(pose_ref),
        "returncode": returncode,
        "pose_execution_source": (
            "existing_pose_artifact" if reused_existing_pose else "engine_command"
        ),
        "predicted_ligand_checksum": pose_checksum,
        "score": score,
        "score_source": score_source,
        "symmetry_aware_rmsd_angstrom": rmsd,
        "pose_success": updated_receipt["pose_success"],
        "blockers": blockers,
    }


def run_public_benchmark_vina_gnina_engine_run_receipts(
    *,
    repo_root: Path = ROOT,
    engine_run_bundle: Path = DEFAULT_ENGINE_RUN_BUNDLE,
    input_manifest: Path = DEFAULT_INPUT_MANIFEST,
    out_report: Path = DEFAULT_OUT_REPORT,
    engines: set[str] | None = None,
    case_ids: set[str] | None = None,
    limit: int | None = None,
    timeout_seconds: int = 900,
    force: bool = False,
    reuse_existing_poses: bool = False,
) -> dict[str, Any]:
    bundle = _load_json(repo_root, engine_run_bundle)
    manifest_rows = _read_manifest(repo_root, input_manifest)
    selected_rows = [
        row
        for row in _as_list(bundle.get("bundle_rows"))
        if isinstance(row, dict)
        and (not engines or _required_text(row.get("engine_id")) in engines)
        and (not case_ids or _required_text(row.get("case_id")) in case_ids)
    ]
    if limit is not None:
        selected_rows = selected_rows[: max(0, limit)]
    run_rows = [
        _run_bundle_row(
            repo_root=repo_root,
            bundle_row=row,
            manifest_rows=manifest_rows,
            timeout_seconds=timeout_seconds,
            force=force,
            reuse_existing_poses=reuse_existing_poses,
        )
        for row in selected_rows
    ]
    blockers = [
        f"{row['run_key']}::{blocker}"
        for row in run_rows
        for blocker in _as_list(row.get("blockers"))
    ]
    completed_count = sum(1 for row in run_rows if row.get("status") == "engine_run_complete")
    skipped_count = sum(1 for row in run_rows if row.get("status") == "skipped_complete")
    status = "engine_run_receipts_complete" if run_rows and not blockers else "engine_run_receipts_blocked"
    report = {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            repo_root=repo_root,
            input_paths=[
                Path("scripts/run_public_benchmark_vina_gnina_engine_run_receipts.py"),
                engine_run_bundle,
                input_manifest,
            ],
            reused_evidence=False,
            reuse_policy="public_benchmark_vina_gnina_engine_run_receipts_completed_from_local_engine_runs",
        ),
        "status": status,
        "contract_pass": bool(run_rows and not blockers),
        "engine_run_bundle_artifact": str(engine_run_bundle),
        "input_manifest": str(input_manifest),
        "out_report_artifact": str(out_report),
        "selected_run_count": len(selected_rows),
        "completed_run_count": completed_count,
        "skipped_complete_count": skipped_count,
        "blocked_run_count": len(run_rows) - completed_count - skipped_count,
        "blockers": blockers,
        "run_rows": run_rows,
        "summary": {
            "selected_run_count": len(selected_rows),
            "completed_run_count": completed_count,
            "skipped_complete_count": skipped_count,
            "blocked_run_count": len(run_rows) - completed_count - skipped_count,
            "blocker_count": len(blockers),
        },
        "claim_boundary": (
            "This report is generated from local Vina/GNINA command execution and "
            "receipt completion. It does not replace downstream adapter and Phase 2 "
            "row-audit validation."
        ),
    }
    _write_json(repo_root, out_report, report)
    return report


def _csv_set(values: str) -> set[str] | None:
    parsed = {value.strip() for value in values.split(",") if value.strip()}
    return parsed or None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--engine-run-bundle", type=Path, default=DEFAULT_ENGINE_RUN_BUNDLE)
    parser.add_argument("--input-manifest", type=Path, default=DEFAULT_INPUT_MANIFEST)
    parser.add_argument("--out-report", type=Path, default=DEFAULT_OUT_REPORT)
    parser.add_argument("--engines", default="")
    parser.add_argument("--case-ids", default="")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--reuse-existing-poses", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = run_public_benchmark_vina_gnina_engine_run_receipts(
        repo_root=args.repo_root,
        engine_run_bundle=args.engine_run_bundle,
        input_manifest=args.input_manifest,
        out_report=args.out_report,
        engines=_csv_set(args.engines),
        case_ids=_csv_set(args.case_ids),
        limit=args.limit,
        timeout_seconds=args.timeout_seconds,
        force=args.force,
        reuse_existing_poses=args.reuse_existing_poses,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "public-benchmark-vina-gnina-engine-run-receipts: "
            f"{payload['status']} | selected={payload['selected_run_count']} | "
            f"complete={payload['completed_run_count']} | "
            f"skipped={payload['skipped_complete_count']} | "
            f"blockers={len(payload['blockers'])}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
