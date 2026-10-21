#!/usr/bin/env python3
"""Compare the existing Python material/RC APIs with explicit native execution.

Run this same driver in separate processes with baseline and candidate PYTHONPATHs.
Results are volatile timing observations, not physical or release qualification.
"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import time


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def measure(function, repetitions, fingerprint):
    first_started = time.perf_counter_ns()
    first = function()
    first_ns = time.perf_counter_ns() - first_started
    first_hash = fingerprint(first)
    sample_hashes = []
    samples = []
    for _ in range(repetitions):
        started = time.perf_counter_ns()
        value = function()
        samples.append(time.perf_counter_ns() - started)
        observed_hash = fingerprint(value)
        sample_hashes.append(observed_hash)
        if observed_hash != first_hash:
            raise RuntimeError("timed sample output differs from the first call")
    return (
        value,
        {
            "first_call_ns": first_ns,
            "first_output_sha256": first_hash,
            "sample_output_sha256": sample_hashes,
            "samples_ns": samples,
            "median_ns": statistics.median(samples),
            "stdev_ns": statistics.pstdev(samples),
        },
        first,
    )


def material_cases(backend, repetitions, emit=None):
    from structural_analysis.materials.uniaxial_plasticity import (
        BilinearCombinedHardeningSteel,
    )

    rows = []
    for count in (250, 1000, 4000, 16000, 64000):
        print(f"starting material points={count}", flush=True)
        laws = [
            BilinearCombinedHardeningSteel(yield_stress_mpa=200 + i % 11)
            for i in range(count)
        ]
        # Parents include an accepted plastic excursion before reversal.
        parents = [law.integrate(0.002, law.initial_state()).state for law in laws]
        strains = [(-0.003 if i % 2 else 0.0025) for i in range(count)]

        def evaluate():
            if backend is not None:
                return backend.integrate(laws, strains, parents)
            return tuple(
                law.integrate(strain, parent)
                for law, strain, parent in zip(laws, strains, parents, strict=True)
            )

        saved = [parent.canonical_bytes() for parent in parents]
        result, timing, first = measure(
            evaluate,
            repetitions,
            lambda values: digest([row.to_dict() for row in values]),
        )
        assert saved == [parent.canonical_bytes() for parent in parents]
        output = digest([row.to_dict() for row in result])
        assert output == digest([row.to_dict() for row in first])
        rows.append(
            {
                "scope": "steel_batch_full_response_api",
                "points": count,
                "input_sha256": digest(
                    {
                        "strains": strains,
                        "materials": [asdict(law) for law in laws],
                        "parents": [raw.hex() for raw in saved],
                    }
                ),
                "output_sha256": output,
                "parent_immutable": True,
                **timing,
            }
        )
        if emit is not None:
            emit(rows[-1])
    return rows


def section_cases(backend, repetitions, emit=None):
    from structural_analysis.materials.stateful_fiber_section import (
        StatefulRCFiberSection,
        StatefulSectionFiber,
    )

    rows = []
    for count in (8, 32, 128, 512, 2048):
        print(f"starting section steel_points={count}", flush=True)
        fibers = tuple(
            StatefulSectionFiber(
                f"steel-{i:05d}",
                -0.25 + 0.5 * i / max(count - 1, 1),
                0.003 / count,
                "steel",
            )
            for i in range(count)
        ) + (
            StatefulSectionFiber("concrete-a", -0.15, 0.08, "concrete"),
            StatefulSectionFiber("concrete-b", 0.15, 0.08, "concrete"),
        )
        section = StatefulRCFiberSection(fibers=fibers)
        parent = section.initial_state()
        saved = parent.canonical_bytes()

        def evaluate():
            return section.integrate((0.002, 0.004), parent)

        result, timing, first = measure(
            evaluate, repetitions, lambda response: digest(response.to_dict())
        )
        assert parent.canonical_bytes() == saved
        output = digest(result.to_dict())
        assert output == digest(first.to_dict())
        rows.append(
            {
                "scope": "existing_rc_section_integrate",
                "steel_points": count,
                "input_sha256": digest(
                    {
                        "section": section.contract_hash,
                        "parent": saved.hex(),
                        "strain": [0.002, 0.004],
                    }
                ),
                "output_sha256": output,
                "parent_immutable": True,
                **timing,
            }
        )
        if emit is not None:
            emit(rows[-1])
    return rows


def public_payload(members, layers):
    payload = {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": [
            {"id": f"N{i}", "coordinates": [3.0 * i, 0.0, 0.0]}
            for i in range(members + 1)
        ],
        "elements": [
            {
                "id": f"M{i}",
                "type": "stateful_rc_fiber_frame2d",
                "nodes": [f"N{i}", f"N{i + 1}"],
                "section": "RC1",
                "integration_order": 2,
            }
            for i in range(members)
        ],
        "materials": [
            {
                "id": "steel",
                "type": "bilinear_combined_hardening_steel",
                "elastic_modulus_mpa": 200000.0,
                "yield_stress_mpa": 250.0,
                "isotropic_hardening_modulus_mpa": 3000.0,
                "kinematic_hardening_modulus_mpa": 5000.0,
                "yield_tolerance_mpa": 1e-10,
            },
            {
                "id": "concrete",
                "type": "asymmetric_concrete_damage",
                "elastic_modulus_mpa": 30000.0,
                "tensile_strength_mpa": 3.0,
                "compressive_strength_mpa": 30.0,
                "tensile_softening_rate": 3000.0,
                "compressive_softening_rate": 400.0,
                "history_tolerance": 1e-14,
            },
        ],
        "sections": [
            {
                "id": "RC1",
                "type": "rectangular_rc_fiber_section",
                "width_m": 0.4,
                "depth_m": 0.6,
                "cover_m": 0.05,
                "concrete_layer_count": layers,
                "top_bar_count": 4,
                "bottom_bar_count": 4,
                "bar_area_m2": 3.87e-4,
                "steel_material": "steel",
                "concrete_material": "concrete",
            }
        ],
        "loads": [
            {
                "node": f"N{members}",
                "components": {
                    "FX": 0.0,
                    "FY": -10.0 / members**3,
                    "FZ": 0.0,
                    "MX": 0.0,
                    "MY": 0.0,
                    "MZ": 0.0,
                },
            }
        ],
        "supports": [{"node": "N0", "dofs": ["UX", "UY", "RZ"]}],
        "unsupported_features": [],
        "warnings": [],
        "metadata": {"case_id": f"performance-serial-{members}-layers-{layers}"},
    }
    return payload


PUBLIC_MAX_MEMBERS = 1


def public_cases(backend, repetitions, emit=None):
    from structural_analysis.api.nonlinear_fiber_frame import (
        PublicRCFiberFrameConfig,
        analyze_public_rc_fiber_frame,
        validate_public_rc_fiber_frame_result,
    )
    from structural_analysis.io.neutral.loader import load_neutral_json_bytes

    rows = []
    for members, layers in ((1, 2), (2, 8), (4, 16)):
        if members > PUBLIC_MAX_MEMBERS:
            continue
        print(f"starting public members={members} layers={layers}", flush=True)
        payload = public_payload(members, layers)
        model = load_neutral_json_bytes(json.dumps(payload).encode())
        config = PublicRCFiberFrameConfig(load_steps=2)

        def evaluate():
            result = analyze_public_rc_fiber_frame(model, config)
            report = validate_public_rc_fiber_frame_result(result)
            if result.status != "ready" or not report.contract_pass:
                raise RuntimeError(
                    "public RC benchmark did not pass its existing gates"
                )
            return result

        def numerical_fingerprint(value):
            normalized = value.to_dict()
            normalized.pop("result_hash", None)
            normalized["configuration"].pop("material_execution_backend", None)
            return digest(
                {
                    "numerical_result": normalized,
                    "checkpoint": hashlib.sha256(
                        value.checkpoint_artifact()
                    ).hexdigest(),
                }
            )

        result, timing, first = measure(evaluate, repetitions, numerical_fingerprint)
        normalized = result.to_dict()
        normalized.pop("result_hash", None)
        normalized["configuration"].pop("material_execution_backend", None)
        rows.append(
            {
                "scope": "public_rc_analyze_and_validate",
                "members": members,
                "concrete_layers": layers,
                "input_sha256": digest(payload),
                "output_sha256": digest(normalized),
                "checkpoint_sha256": hashlib.sha256(
                    result.checkpoint_artifact()
                ).hexdigest(),
                "first_checkpoint_sha256": hashlib.sha256(
                    first.checkpoint_artifact()
                ).hexdigest(),
                "status": result.status,
                "fallback_count": result.metrics["fallback_count"],
                "regularization_count": result.metrics["regularization_count"],
                **timing,
            }
        )
        if emit is not None:
            emit(rows[-1])
    return rows


def main():
    global PUBLIC_MAX_MEMBERS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--library", type=Path)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--public-max-members", type=int, choices=(1, 2, 4), default=1)
    parser.add_argument(
        "--suite", choices=("material", "section", "public", "all"), default="all"
    )
    args = parser.parse_args()
    PUBLIC_MAX_MEMBERS = args.public_max_members
    if not 3 <= args.repetitions <= 20:
        parser.error("repetitions must be 3..20")
    import structural_analysis.materials.uniaxial_plasticity as material_module
    import structural_analysis.materials.stateful_fiber_section as section_module

    backend = None
    context = nullcontext()
    if args.library:
        from structural_analysis.materials.native_steel_batch import (
            NativeSteelBatch,
            use_native_steel_batch,
        )

        backend = NativeSteelBatch(args.library, workers=args.workers)
        context = use_native_steel_batch(backend)
    sources = [Path(material_module.__file__), Path(section_module.__file__)]
    root = sources[0].parents[3]
    rows = []
    report = {
        "schema": "native-steel-performance.v2",
        "source_root": str(root),
        "source_head": subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip(),
        "source_dirty": bool(
            subprocess.check_output(
                ["git", "-C", str(root), "status", "--porcelain=v1"]
            )
        ),
        "source_files": {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sources
        },
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "backend": (
            {
                **backend.metadata(),
                "last_observed_workers": backend.last_observed_workers,
            }
            if backend
            else {"backend": "python_reference"}
        ),
        "machine": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpus": os.cpu_count(),
            "affinity": sorted(os.sched_getaffinity(0)),
        },
        "thread_settings": {
            k: os.environ.get(k)
            for k in (
                "OPENBLAS_NUM_THREADS",
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
                "OMP_WAIT_POLICY",
            )
        },
        "measurement": {
            "clock": "perf_counter_ns",
            "warmup_calls": 1,
            "repetitions": args.repetitions,
            "timed_scope": "same returned API values; public includes validation; model/parent setup outside timing",
            "cross_run_parity_required": True,
            "all_samples_fingerprinted_outside_timing": True,
            "first_call_is_process_cold": False,
        },
        "rows": rows,
        "status": "running",
        "claim_boundary": "Generated material/section and bounded public RC cases; not experimental validation or whole-product speedup.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")

    def save_row(row):
        rows.append(row)
        if backend:
            report["backend"] = {
                **backend.metadata(),
                "last_observed_workers": backend.last_observed_workers,
            }
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        print(
            json.dumps(
                {"completed_scope": row["scope"], "median_ns": row["median_ns"]}
            ),
            flush=True,
        )

    try:
        with context:
            for name, function in (
                ("material", material_cases),
                ("section", section_cases),
                ("public", public_cases),
            ):
                if args.suite in (name, "all"):
                    function(backend, args.repetitions, emit=save_row)
        report["status"] = "completed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "rows": len(rows),
                "backend": report["backend"],
            }
        )
    )


if __name__ == "__main__":
    main()
