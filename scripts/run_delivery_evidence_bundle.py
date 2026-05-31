#!/usr/bin/env python3
"""Run delivery evidence gates (reanalysis, proxy, commercial crossval) and bundle JSON."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=REPO_ROOT, check=False, capture_output=True, text=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/release_evidence/productization/delivery_evidence_bundle.json",
    )
    parser.add_argument(
        "--changes-json",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/release_evidence/productization/design_optimization_cost_reduction_changes.json",
    )
    parser.add_argument(
        "--roundtrip-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json",
    )
    parser.add_argument(
        "--cases-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/commercial_benchmark_cases.from_csv.json",
    )
    parser.add_argument("--enrich-changes", action="store_true", help="Run member_alignment enrich first.")
    parser.add_argument(
        "--parse-roundtrip",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Re-parse optimized MGT into roundtrip JSON+NPZ (default on; use --no-parse-roundtrip for sha-only).",
    )
    args = parser.parse_args()
    out_dir = args.output_json.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    steps: list[dict[str, object]] = []
    mgt_path = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"
    sync_out = out_dir / "mgt_roundtrip_sync.json"
    sync_cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts/sync_optimized_mgt_roundtrip.py"),
        "--mgt",
        str(mgt_path),
        "--roundtrip-json",
        str(args.roundtrip_json),
        "--output-json",
        str(sync_out),
    ]
    if args.parse_roundtrip:
        sync_cmd.append("--parse")
    else:
        sync_cmd.append("--sync-only")
    code, log = _run(sync_cmd)
    steps.append({"step": "mgt_roundtrip_sync", "exit_code": code, "log": log})

    global_fea_out = out_dir / "mgt_global_fea_readiness_gate.json"
    mgt_fingerprint_out = out_dir / "mgt_roundtrip_assembly_fingerprint.json"
    mgt_mesh_contract_out = out_dir / "mgt_global_fea_mesh_contract_gate.json"
    rh_html_out = out_dir / "rh_engineer_review_packet_template.html"
    rh_checklist_out = out_dir / "rh_closure_checklist.json"
    rh_template_out = out_dir / "rh_signed_closure_packet_template.json"
    ml_status_out = out_dir / "ml_multi_objective_status.json"
    productization_validate_out = out_dir / "productization_delivery_evidence_validation.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_global_fea_readiness_gate.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(global_fea_out),
        ]
    )
    steps.append({"step": "mgt_global_fea_readiness", "exit_code": code, "log": log})

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_mgt_roundtrip_assembly_fingerprint.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(mgt_fingerprint_out),
        ]
    )
    steps.append({"step": "mgt_roundtrip_assembly_fingerprint", "exit_code": code, "log": log})

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_global_fea_mesh_contract_gate.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(mgt_mesh_contract_out),
        ]
    )
    steps.append({"step": "mgt_global_fea_mesh_contract", "exit_code": code, "log": log})
    mesh_contract_exit = code

    pareto_archive_out = out_dir / "optimization_pareto_research_archive.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_optimization_pareto_research_archive.py"),
            "--changes-json",
            str(args.changes_json),
            "--output-json",
            str(pareto_archive_out),
        ]
    )
    steps.append({"step": "optimization_pareto_research_archive", "exit_code": code, "log": log})

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/report_ml_multi_objective_status.py"),
            "--output-json",
            str(ml_status_out),
        ]
    )
    steps.append({"step": "ml_multi_objective_status", "exit_code": code, "log": log})

    if args.enrich_changes:
        code, log = _run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts/enrich_optimization_changes_contract.py"),
                "--changes-json",
                str(args.changes_json),
            ]
        )
        steps.append({"step": "enrich_member_alignment", "exit_code": code, "log": log})

    crossval_out = out_dir / "commercial_solver_cross_validation.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/report_commercial_solver_cross_validation.py"),
            "--cases-json",
            str(args.cases_json),
            "--output-json",
            str(crossval_out),
        ]
    )
    steps.append({"step": "commercial_cross_validation", "exit_code": code, "log": log})

    proxy_out = out_dir / "proxy_solver_divergence_gate.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_proxy_solver_divergence_gate.py"),
            "--changes-json",
            str(args.changes_json),
            "--output-json",
            str(proxy_out),
        ]
    )
    steps.append({"step": "proxy_solver_divergence", "exit_code": code, "log": log})

    mgt_pipeline_out = out_dir / "mgt_native_reanalysis_pipeline.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_native_reanalysis_pipeline.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--changes-json",
            str(args.changes_json),
            "--output-json",
            str(mgt_pipeline_out),
            "--sync-provenance",
        ]
        + (["--refresh-parse"] if args.parse_roundtrip else [])
    )
    steps.append({"step": "mgt_native_reanalysis_pipeline", "exit_code": code, "log": log})

    mgt_3d_out = out_dir / "mgt_global_fea_3d_native_solve.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_global_fea_3d_native_solve.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(mgt_3d_out),
            "--commercial-crossval-json",
            str(out_dir / "commercial_solver_cross_validation.json"),
        ]
    )
    steps.append({"step": "mgt_global_fea_3d_native_solve", "exit_code": code, "log": log})

    mgt_condensed_out = out_dir / "mgt_global_fea_condensed_solve.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_global_fea_condensed_solve.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(mgt_condensed_out),
        ]
    )
    steps.append({"step": "mgt_global_fea_condensed_solve", "exit_code": code, "log": log})

    resolve_code, resolve_log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/resolve_midas_same_mesh_result_path.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
        ]
    )
    midas_resolution_kind = "default_proxy"
    if resolve_code == 0 and resolve_log:
        first_line = resolve_log.splitlines()[0]
        parts = first_line.split("\t", 1)
        midas_result_out = Path(parts[0])
        midas_resolution_kind = parts[1] if len(parts) > 1 else midas_resolution_kind
    else:
        midas_result_out = (
            REPO_ROOT
            / "implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_same_mesh_result.json"
        )
    steps.append(
        {
            "step": "midas_same_mesh_result_resolve",
            "exit_code": resolve_code,
            "log": resolve_log,
            "resolution_kind": midas_resolution_kind,
        }
    )

    if midas_resolution_kind in {"missing", "default_proxy", "proxy_sibling"}:
        code, log = _run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts/build_midas_gen_same_mesh_result_proxy.py"),
                "--roundtrip-json",
                str(args.roundtrip_json),
                "--commercial-crossval-json",
                str(out_dir / "commercial_solver_cross_validation.json"),
                "--output-json",
                str(midas_result_out),
            ]
        )
        steps.append({"step": "midas_gen_same_mesh_result_proxy", "exit_code": code, "log": log})

    midas_validate_out = out_dir / "midas_gen_same_mesh_result_validation.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/validate_midas_gen_same_mesh_result.py"),
            "--result-json",
            str(midas_result_out),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(midas_validate_out),
        ]
    )
    steps.append({"step": "midas_gen_same_mesh_result_validation", "exit_code": code, "log": log})

    midas_compare_out = out_dir / "midas_gen_same_mesh_native_comparison.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_midas_gen_same_mesh_native_comparison.py"),
            "--result-json",
            str(midas_result_out),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--native-3d-solve-json",
            str(mgt_3d_out),
            "--native-condensed-solve-json",
            str(mgt_condensed_out),
            "--output-json",
            str(midas_compare_out),
        ]
    )
    steps.append({"step": "midas_gen_same_mesh_native_comparison", "exit_code": code, "log": log})

    gpu_equiv_out = out_dir / "gpu_production_newton_equivalence_gate.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_gpu_production_newton_equivalence_gate.py"),
            "--output-json",
            str(gpu_equiv_out),
        ]
    )
    steps.append({"step": "gpu_production_newton_equivalence_gate", "exit_code": code, "log": log})

    gpu_newton_cert_out = out_dir / "gpu_newton_terminal_certification.json"
    equiv_arg = ["--production-equivalence-json", str(gpu_equiv_out)] if gpu_equiv_out.is_file() else []
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_gpu_newton_terminal_certification.py"),
            "--output-json",
            str(gpu_newton_cert_out),
        ]
        + equiv_arg
    )
    steps.append({"step": "gpu_newton_terminal_certification", "exit_code": code, "log": log})

    gpu_claim_out = out_dir / "gpu_solver_claim_receipt.json"
    gpu_cert_arg = ["--terminal-certification-json", str(gpu_newton_cert_out)] if gpu_newton_cert_out.is_file() else []
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_gpu_solver_claim_receipt.py"),
            "--output-json",
            str(gpu_claim_out),
        ]
        + gpu_cert_arg
    )
    steps.append({"step": "gpu_solver_claim_receipt", "exit_code": code, "log": log})

    gpu_newton_checklist_out = out_dir / "gpu_newton_certification_checklist.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_gpu_newton_certification_checklist.py"),
            "--output-json",
            str(gpu_newton_checklist_out),
        ]
        + gpu_cert_arg
    )
    steps.append({"step": "gpu_newton_certification_checklist", "exit_code": code, "log": log})

    story_out = out_dir / "story_model_reanalysis.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_story_model_reanalysis.py"),
            "--state-npz",
            str(
                REPO_ROOT
                / "implementation/phase1/release/design_optimization/design_optimization_solver_loop_state.npz"
            ),
            "--changes-json",
            str(args.changes_json),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(story_out),
        ]
    )
    steps.append({"step": "story_model_reanalysis", "exit_code": code, "log": log})

    reanalysis_out = out_dir / "post_optimization_reanalysis_gate.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_post_optimization_reanalysis_gate.py"),
            "--optimized-roundtrip-json",
            str(args.roundtrip_json),
            "--changes-json",
            str(args.changes_json),
            "--output-json",
            str(reanalysis_out),
            "--require-changes",
            "--run-story-reanalysis",
            "--sync-mgt-provenance",
        ]
    )
    steps.append({"step": "post_optimization_reanalysis", "exit_code": code, "log": log})

    artifacts = {
        "commercial_cross_validation": str(crossval_out) if crossval_out.is_file() else "",
        "proxy_solver_divergence": str(proxy_out) if proxy_out.is_file() else "",
        "story_model_reanalysis": str(story_out) if story_out.is_file() else "",
        "gpu_solver_claim_receipt": str(gpu_claim_out) if gpu_claim_out.is_file() else "",
        "mgt_native_reanalysis_pipeline": str(mgt_pipeline_out) if mgt_pipeline_out.is_file() else "",
        "mgt_global_fea_condensed_solve": str(mgt_condensed_out) if mgt_condensed_out.is_file() else "",
        "gpu_newton_terminal_certification": str(gpu_newton_cert_out) if gpu_newton_cert_out.is_file() else "",
        "post_optimization_reanalysis": str(reanalysis_out) if reanalysis_out.is_file() else "",
        "mgt_roundtrip_sync": str(sync_out) if sync_out.is_file() else "",
        "mgt_global_fea_readiness": str(global_fea_out) if global_fea_out.is_file() else "",
        "rh_closure_checklist": str(rh_checklist_out) if rh_checklist_out.is_file() else "",
        "changes_json": str(args.changes_json),
    }

    def _load(path: Path) -> dict:
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    crossval = _load(crossval_out)
    proxy = _load(proxy_out)
    story_payload = _load(story_out)
    story_receipt = story_payload.get("story_model_reanalysis") if isinstance(story_payload, dict) else {}
    mgt_pipeline = _load(mgt_pipeline_out)
    global_fea = _load(global_fea_out)
    reanalysis = _load(reanalysis_out)
    changes = _load(args.changes_json)
    alignment = changes.get("member_alignment") if isinstance(changes.get("member_alignment"), dict) else {}

    blockers: list[str] = []
    if mesh_contract_exit != 0:
        blockers.append("mgt_mesh_contract_blocked")
    crossval_ok_statuses = {"pass", "partial", "pass_with_marginal_metrics", "partial_marginal_only"}
    if crossval.get("status") not in crossval_ok_statuses:
        blockers.append("commercial_cross_validation_not_pass")
    if int(crossval.get("metric_failures_hard") or 0) > 0:
        blockers.append("commercial_cross_validation_hard_failures")
    if global_fea.get("status") == "blocked":
        blockers.append("mgt_global_fea_readiness_blocked")
    if proxy.get("divergence_count", 0) > 0:
        blockers.append("proxy_solver_divergence_present")
    if reanalysis.get("blockers"):
        blockers.extend(str(item) for item in reanalysis.get("blockers") or [])

    bundle = {
        "schema_version": "delivery-evidence-bundle.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if not blockers else "review_required",
        "claim": "Engineer-in-loop delivery evidence bundle; not permit approval.",
        "steps": steps,
        "artifacts": artifacts,
        "summary": {
            "cross_validation_status": crossval.get("status"),
            "cross_validation_marginal_accepted": crossval.get("metric_marginal_accepted"),
            "cross_validation_hard_failures": crossval.get("metric_failures_hard"),
            "mgt_roundtrip_sync_status": _load(sync_out).get("status") if sync_out.is_file() else "",
            "mgt_roundtrip_parsed": bool((_load(sync_out).get("parse") or {}).get("contract_pass")),
            "global_fea_readiness_status": global_fea.get("status"),
            "global_fea_readiness_ready": global_fea.get("readiness_for_global_fea_wiring"),
            "proxy_divergence_count": proxy.get("divergence_count"),
            "reanalysis_status": reanalysis.get("status"),
            "story_reanalysis_status": story_receipt.get("status"),
            "mgt_pipeline_status": mgt_pipeline.get("status"),
            "native_fea_solve_status": ((mgt_pipeline.get("native_fea") or {}).get("native_solve_status")),
            "mgt_condensed_solve_status": _load(mgt_condensed_out).get("native_solve_status"),
            "mgt_integrity_status": (mgt_pipeline.get("mgt_integrity") or {}).get("integrity_status"),
            "member_alignment_status": alignment.get("alignment_status"),
            "removed_member_count": len(alignment.get("removed_member_ids") or []),
        },
        "blockers": blockers,
        "holdout_evidence_hints": {
            "RH-002": {
                "supplementary_artifact": str(crossval_out),
                "note": "Commercial HF/LF cross-validation supports legacy-tool comparison workflow.",
            },
            "RH-001": {
                "supplementary_artifact": str(reanalysis_out),
                "note": "Post-optimization reanalysis gate records story-proxy safety metrics.",
            },
            "RH-003": {
                "supplementary_artifact": str(story_out),
                "note": "Story-model reanalysis receipt with MGT provenance for authority workflow review.",
            },
        },
    }
    rh_path = REPO_ROOT / "implementation/phase1/release_evidence/productization/residual_holdout_closure_updates.json"
    args.output_json.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_rh_closure_checklist.py"),
            "--rh-json",
            str(rh_path),
            "--bundle-json",
            str(args.output_json),
            "--output-json",
            str(rh_checklist_out),
        ]
    )
    steps.append({"step": "rh_closure_checklist", "exit_code": code, "log": log})

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_rh_signed_closure_packet_template.py"),
            "--rh-json",
            str(rh_path),
            "--checklist-json",
            str(rh_checklist_out),
            "--output-json",
            str(rh_template_out),
        ]
    )
    steps.append({"step": "rh_signed_closure_packet_template", "exit_code": code, "log": log})

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_rh_engineer_review_packet_html.py"),
            "--template-json",
            str(rh_template_out),
            "--bundle-json",
            str(args.output_json),
            "--output-html",
            str(rh_html_out),
        ]
    )
    steps.append({"step": "rh_engineer_review_packet_html", "exit_code": code, "log": log})

    bundle["steps"] = steps
    bundle["artifacts"]["rh_closure_checklist"] = str(rh_checklist_out) if rh_checklist_out.is_file() else ""
    bundle["artifacts"]["rh_signed_closure_packet_template"] = (
        str(rh_template_out) if rh_template_out.is_file() else ""
    )
    bundle["artifacts"]["gpu_newton_certification_checklist"] = (
        str(gpu_newton_checklist_out) if gpu_newton_checklist_out.is_file() else ""
    )
    bundle["artifacts"]["gpu_newton_terminal_certification"] = (
        str(gpu_newton_cert_out) if gpu_newton_cert_out.is_file() else ""
    )
    bundle["artifacts"]["mgt_global_fea_condensed_solve"] = (
        str(mgt_condensed_out) if mgt_condensed_out.is_file() else ""
    )
    bundle["artifacts"]["mgt_global_fea_3d_native_solve"] = str(mgt_3d_out) if mgt_3d_out.is_file() else ""
    bundle["artifacts"]["gpu_production_newton_equivalence_gate"] = (
        str(gpu_equiv_out) if gpu_equiv_out.is_file() else ""
    )
    bundle["artifacts"]["residual_holdout_closure_updates"] = str(rh_path) if rh_path.is_file() else ""
    args.output_json.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/sync_holdout_supplementary_evidence.py"),
            "--bundle-json",
            str(args.output_json),
            "--residual-holdout-json",
            str(rh_path),
            "--output-json",
            str(rh_path),
        ]
    )
    steps.append({"step": "sync_holdout_supplementary", "exit_code": code, "log": log})

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/finalize_rh_signed_closure.py"),
            "--bundle-json",
            str(args.output_json),
            "--rh-json",
            str(rh_path),
            "--output-json",
            str(rh_path),
        ]
    )
    steps.append({"step": "finalize_rh_signed_closure", "exit_code": code, "log": log})

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_rh_closure_checklist.py"),
            "--rh-json",
            str(rh_path),
            "--bundle-json",
            str(args.output_json),
            "--output-json",
            str(rh_checklist_out),
        ]
    )
    steps.append({"step": "rh_closure_checklist_post_sign", "exit_code": code, "log": log})

    bundle["steps"] = steps
    bundle["artifacts"]["rh_closure_checklist"] = str(rh_checklist_out) if rh_checklist_out.is_file() else ""
    rh_closed = _load(rh_path).get("rh_closure_status") == "closed"
    if not rh_closed:
        blockers.append("rh_signed_closure_incomplete")
    mesh_3d_status = _load(mgt_3d_out).get("native_solve_status")
    if mesh_3d_status not in {"mesh_3d_beam_global_wired", "mesh_3d_beam_global_wired_with_licensed_fingerprint_bridge"}:
        blockers.append("mgt_global_fea_3d_native_solve_not_wired")
    condensed_status = _load(mgt_condensed_out).get("native_solve_status")
    if condensed_status != "condensed_global_fea_wired":
        blockers.append("mgt_global_fea_condensed_solve_not_wired")
    gpu_equiv = _load(gpu_equiv_out)
    if not gpu_equiv.get("production_newton_equivalent_to_closed_form"):
        blockers.append("gpu_production_newton_not_equivalent")
    gpu_cert = _load(gpu_newton_cert_out)
    if not gpu_cert.get("gpu_newton_terminal_proven"):
        blockers.append("gpu_newton_terminal_not_certified")
    bundle["status"] = "ready" if not blockers else "review_required"
    bundle["blockers"] = blockers
    args.output_json.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")

    gap_status_out = out_dir / "gap_closure_status.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/report_gap_closure_status.py"),
            "--output-json",
            str(gap_status_out),
        ]
    )
    steps.append({"step": "gap_closure_status", "exit_code": code, "log": log})

    bundle["steps"] = steps
    bundle["artifacts"]["gap_closure_status"] = str(gap_status_out) if gap_status_out.is_file() else ""
    bundle["artifacts"]["mgt_roundtrip_assembly_fingerprint"] = (
        str(mgt_fingerprint_out) if mgt_fingerprint_out.is_file() else ""
    )
    bundle["artifacts"]["mgt_global_fea_mesh_contract"] = (
        str(mgt_mesh_contract_out) if mgt_mesh_contract_out.is_file() else ""
    )
    bundle["artifacts"]["rh_engineer_review_packet_html"] = str(rh_html_out) if rh_html_out.is_file() else ""
    bundle["artifacts"]["ml_multi_objective_status"] = str(ml_status_out) if ml_status_out.is_file() else ""
    bundle["status"] = "ready" if not blockers else "review_required"
    bundle["blockers"] = blockers
    args.output_json.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/validate_productization_delivery_evidence.py"),
            "--productization-dir",
            str(out_dir),
            "--output-json",
            str(productization_validate_out),
        ]
    )
    steps.append({"step": "productization_delivery_evidence_validation", "exit_code": code, "log": log})
    if code != 0 and "productization_validation_failed" not in blockers:
        blockers.append("productization_validation_failed")
        bundle["status"] = "review_required"
        bundle["blockers"] = blockers
        args.output_json.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    bundle["artifacts"]["productization_delivery_evidence_validation"] = (
        str(productization_validate_out) if productization_validate_out.is_file() else ""
    )

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/report_gap_closure_status.py"),
            "--output-json",
            str(gap_status_out),
        ]
    )
    steps.append({"step": "gap_closure_status_final", "exit_code": code, "log": log})
    bundle["steps"] = steps
    args.output_json.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    print(f"bundle: {bundle['status']} -> {args.output_json}")
    if blockers:
        print(f"bundle: blockers={','.join(blockers)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
