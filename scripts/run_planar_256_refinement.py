"""Frozen-source, research-only full-history section refinement observation.

Keeps the existing proportional load vector, forty targets and solver defaults.
The source snapshot must match both its fixed manifest and its actual Git tree.
No benchmark speedup, public API extension or physical qualification is implied.
"""

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from time import perf_counter_ns

SOURCE_REVISION = "3e2cc1dba5c6dac1b12eb1badc9b6df09337b847"
MANIFEST_SHA256 = "5cebb7cfcb4dce2228e59fd2006d198bc27afc7e6ad567cf2621d6fbc4d54b6a"
INPUT_SHA256 = "34822feaee8f569712b46e5842f5fcc3253a9a851bb9a13c92624be238b4c23e"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def write_path_artifacts(root, metadata, steps):
    """Preserve the original full JSON bytes while materializing one step at a time.

    Metadata is the original ordered dictionary with an empty steps placeholder.
    The index is published only after all full/step files finish successfully.
    """
    require(type(metadata.get('steps')) is list and not metadata['steps'],
            'empty steps placeholder required')
    step_root = root / 'steps'
    step_root.mkdir()
    encoder = json.JSONEncoder(indent=2, allow_nan=False)
    entries = []
    full = root / 'repeat-0.json'
    with full.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write('{')
        for index, (key, value) in enumerate(metadata.items()):
            require(type(key) is str, 'string metadata key required')
            stream.write(',' if index else '')
            stream.write('\n  ' + encoder.encode(key) + ': ')
            if key == 'steps':
                stream.write('[')
                for step in steps:
                    ordinal = len(entries)
                    step_file = step_root / f'{ordinal:04d}.json'
                    write_json(step_file, step)
                    entries.append({'path': str(step_file.relative_to(root)),
                                    'bytes': step_file.stat().st_size,
                                    'sha256': file_sha256(step_file)})
                    stream.write(',' if ordinal else '')
                    stream.write('\n    ')
                    for chunk in encoder.iterencode(step):
                        stream.write(chunk.replace('\n', '\n    '))
                    del step
                if entries:
                    stream.write('\n  ')
                stream.write(']')
            else:
                for chunk in encoder.iterencode(value):
                    stream.write(chunk.replace('\n', '\n  '))
        stream.write('\n}\n')
    meta_file = root / 'path-metadata.json'
    write_json(meta_file, metadata)
    receipt = {'schema': 'fixed-planar-path-file-index.v1',
               'full': {'path': full.name, 'bytes': full.stat().st_size,
                        'sha256': file_sha256(full)},
               'metadata': {'path': meta_file.name, 'bytes': meta_file.stat().st_size,
                            'sha256': file_sha256(meta_file)},
               'steps': entries, 'step_count': len(entries)}
    write_json(root / 'path-index.json', receipt)
    return receipt


def checked_sources(bundle, repo):
    raw = (bundle / "inputs-manifest.json").read_bytes()
    require(hashlib.sha256(raw).hexdigest() == MANIFEST_SHA256, "manifest changed")
    manifest = json.loads(raw)
    tree = subprocess.check_output(
        [
            "git",
            "-C",
            str(repo),
            "ls-tree",
            "-r",
            SOURCE_REVISION,
            "--",
            "src/structural_analysis",
        ],
        text=True,
    )
    blobs = {
        line.split("\t")[1].removeprefix("src/structural_analysis/"): line.split()[2]
        for line in tree.splitlines()
    }
    files = {}
    for name, identity in manifest["source_files"].items():
        relative = Path(name)
        require(
            not relative.is_absolute() and ".." not in relative.parts,
            "invalid source path",
        )
        content = (bundle / "source/structural_analysis" / relative).read_bytes()
        require(
            identity
            == {
                "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
                "byte_length": len(content),
            },
            "source identity mismatch",
        )
        git_blob = hashlib.sha1(
            b"blob " + str(len(content)).encode() + b"\0" + content
        ).hexdigest()
        require(blobs.get(name) == git_blob, "source differs from frozen Git tree")
        files[name] = content
    require(len(files) == 461, "unexpected frozen source count")
    model = (bundle / "inputs/case-0003.json").read_bytes()
    require(hashlib.sha256(model).hexdigest() == INPUT_SHA256, "input changed")
    return files, model


def refinement_layers(value):
    require(type(value) is int and value in (256, 512, 1024),
            "predeclared research layer count must be 256, 512 or 1024")
    return value, value // 2


def run(bundle, output_parent, repo, *, layers=256):
    layers, comparison_layers = refinement_layers(layers)
    process_started = perf_counter_ns()
    files, raw = checked_sources(bundle, repo)
    root = Path(
        tempfile.mkdtemp(prefix=f"structural-{layers}-full-refinement-", dir=output_parent)
    )
    print(root, flush=True)
    source_root = root / "source"
    for name, content in files.items():
        path = source_root / "structural_analysis" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (root / "input.json").write_bytes(raw)
    (root / "runner.py").write_bytes(Path(__file__).read_bytes())

    def write(name, value):
        write_json(root / name, value)

    require("structural_analysis" not in sys.modules, "run in a fresh process")
    sys.path.insert(0, str(source_root))
    from structural_analysis.api import nonlinear_frame as api
    from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
        StatefulCorotationalFiberFrame2DDisplacementControlConfig,
        run_stateful_corotational_fiber_frame2d_displacement_control_path,
    )
    from structural_analysis.materials.stateful_fiber_section import (
        make_rectangular_stateful_rc_fiber_section,
    )
    from structural_analysis.model_ir import parse_model_ir_v2

    config = StatefulCorotationalFiberFrame2DDisplacementControlConfig()
    targets = tuple(i / 500 for i in range(1, 41))
    write(
        "protocol.json",
        {
            "schema": f"fixed-planar-{layers}-refinement-protocol.v1",
            "source_revision": SOURCE_REVISION,
            "source_manifest_sha256": MANIFEST_SHA256,
            "source_files_git_verified": len(files),
            "input_sha256": INPUT_SHA256,
            "concrete_layer_count": layers,
            "comparison_layer_count": comparison_layers,
            "target_displacements_m": targets,
            "control_global_dof": 15,
            "configuration": asdict(config),
            "repetitions": 1,
            "same_proportional_force_vector": True,
            "constant_axial_load": False,
            "selection": (
                "Predeclared full 2 through 80 mm history, no retries or tolerance changes. Compare to original 128-layer prefix plus suffix using accepted chains, original nodal/steel groups and equal-area projected concrete histories. Preserve the exploratory 1% screen and local maxima alongside localization descriptors."
                if layers == 256 else
                f"Predeclared full 2 through 80 mm history, no retries or tolerance changes. Compare to the original complete {comparison_layers}-layer path using accepted chains, original nodal/steel groups and equal-area projected concrete histories. Preserve the exploratory 1% screen and local maxima alongside localization descriptors."
            ),
            "physical_validation": False,
            "public_result_authority": False,
            "timing_is_speedup_benchmark": False,
        },
    )
    if layers == 1024:
        require(hashlib.sha256((root / "protocol.json").read_bytes()).hexdigest()
                == "e620f118fc72a7af34b8a527649dcddc3d1b78902922aab2860baa92ba73432b",
                "predeclared 1024-layer protocol changed")
    started = perf_counter_ns()
    model = json.loads(raw)
    require(
        model["nodes"][5]["id"] == "N6"
        and model["nodes"][5]["coordinates_m"] == [4.0, 6.0, 0.0],
        "control node changed",
    )
    doc = parse_model_ir_v2(model, require_analysis_ready=True)
    adapter = api.adapt_bounded_planar_model_ir_v2(doc)
    compiled = api._compile_portal(
        adapter.canonical_model, general_profile=True, source_model_ir_adapter=adapter
    )
    params = model["sections"][0]["parameters"]
    members = []
    for member in compiled.problem.members:
        old = member.element.section
        base = make_rectangular_stateful_rc_fiber_section(
            **params, section_id=old.section_id, steel=old.steel, concrete=old.concrete
        )
        require(base == old, "original section reconstruction mismatch")
        refined = make_rectangular_stateful_rc_fiber_section(
            **dict(params, concrete_layer_count=layers),
            section_id=old.section_id,
            steel=old.steel,
            concrete=old.concrete,
        )
        require(
            refined.fibers[-2:] == old.fibers[-2:], "steel location or area changed"
        )
        members.append(
            replace(member, element=replace(member.element, section=refined))
        )
    problem = replace(compiled.problem, members=tuple(members))
    setup_ns = perf_counter_ns() - started
    print("protocol frozen; starting forty-target solve", flush=True)
    started = perf_counter_ns()
    path = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem, targets, control_global_dof=15, config=config
    )
    solve_ns = perf_counter_ns() - started
    metadata = replace(path, steps=()).to_dict()
    metadata['contract_pass'] = path.contract_pass
    receipt = write_path_artifacts(root, metadata, (step.to_dict() for step in path.steps))
    summary = {
        "source_revision": SOURCE_REVISION,
        "status": path.status,
        "contract_pass": path.contract_pass,
        "attempted_steps": len(path.steps),
        "committed_steps": sum(s.committed for s in path.steps),
        "setup_wall_ns": setup_ns,
        "path_wall_ns": solve_ns,
        "artifact_sha256": receipt['full']['sha256'],
        "through_artifact_hash_wall_ns": perf_counter_ns() - process_started,
        "timing_excludes": "summary and inventory output, subsequent comparison audit",
        "physical_validation": False,
        "public_result_authority": False,
    }
    write("summary.json", summary)
    inventory = [
        {
            "path": str(p.relative_to(root)),
            "bytes": p.stat().st_size,
            "sha256": file_sha256(p),
        }
        for p in sorted(root.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    ]
    write("inventory.json", inventory)
    print(json.dumps(summary), flush=True)
    return root


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output_parent", type=Path)
    parser.add_argument('--layers', type=int, choices=(256, 512, 1024), default=256)
    args = parser.parse_args()
    run(args.bundle, args.output_parent, Path(__file__).resolve().parents[1], layers=args.layers)
