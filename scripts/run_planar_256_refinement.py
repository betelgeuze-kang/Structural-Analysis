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
import shutil
import subprocess
import sys
import tempfile
from time import perf_counter_ns

SOURCE_REVISION = "3e2cc1dba5c6dac1b12eb1badc9b6df09337b847"
MANIFEST_SHA256 = "5cebb7cfcb4dce2228e59fd2006d198bc27afc7e6ad567cf2621d6fbc4d54b6a"
INPUT_SHA256 = "34822feaee8f569712b46e5842f5fcc3253a9a851bb9a13c92624be238b4c23e"
MAX_FULL_JSON_BYTES = 32 * 1024**3
MAX_STEP_JSON_BYTES = 512 * 1024**2
MAX_METADATA_JSON_BYTES = 256 * 1024**2
OUTPUT_FORMAT_RESERVE_BYTES = 1024**3
PROTOCOL_SHA256 = {
    1024: "e620f118fc72a7af34b8a527649dcddc3d1b78902922aab2860baa92ba73432b",
    2048: "6508da674654590141a1b4084b9f59069a70db834da8c4070be153f0dccf9e43",
    4096: "7f30057cd8b26b0706c96bf84d5fc81842c4dbfc319f8abfc5c618793d459881",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


class OutputFormatLimitError(ValueError):
    """A path file would exceed the size accepted by the bounded reader."""


class ByteBoundedWriter:
    def __init__(self, stream, maximum_bytes, label):
        self.stream = stream
        self.maximum_bytes = maximum_bytes
        self.label = label
        self.written_bytes = 0

    def write(self, chunk):
        size = len(chunk.encode('utf-8'))
        if self.written_bytes + size > self.maximum_bytes:
            raise OutputFormatLimitError(
                f'{self.label} exceeds the reader limit of {self.maximum_bytes} bytes'
            )
        result = self.stream.write(chunk)
        self.written_bytes += size
        return result


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value, *, maximum_bytes=None, label=None):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        writer = (ByteBoundedWriter(stream, maximum_bytes, label)
                  if maximum_bytes is not None else stream)
        json.dump(value, writer, indent=2, allow_nan=False)
        writer.write('\n')


def iter_path_json(metadata, steps):
    """Yield the original pretty-printed path bytes without retaining all steps."""
    require(type(metadata.get('steps')) is list and not metadata['steps'],
            'empty steps placeholder required')
    encoder = json.JSONEncoder(indent=2, allow_nan=False)
    yield '{'
    for index, (key, value) in enumerate(metadata.items()):
        require(type(key) is str, 'string metadata key required')
        yield ',' if index else ''
        yield '\n  ' + encoder.encode(key) + ': '
        if key == 'steps':
            yield '['
            count = 0
            for step in steps:
                yield ',' if count else ''
                yield '\n    '
                for chunk in encoder.iterencode(step):
                    yield chunk.replace('\n', '\n    ')
                count += 1
                del step
            if count:
                yield '\n  '
            yield ']'
        else:
            for chunk in encoder.iterencode(value):
                yield chunk.replace('\n', '\n  ')
    yield '\n}\n'


def write_path_artifacts(root, metadata, steps, *, maximum_full_bytes=None,
                         maximum_step_bytes=None, maximum_steps=None):
    """Preserve full JSON bytes and publish the index only after all files finish."""
    require(type(metadata.get('steps')) is list and not metadata['steps'],
            'empty steps placeholder required')
    step_root = root / 'steps'
    step_root.mkdir()
    entries = []

    def recorded_steps():
        for step in steps:
            if maximum_steps is not None and len(entries) >= maximum_steps:
                raise OutputFormatLimitError(
                    f'path exceeds the bounded {maximum_steps}-step output plan'
                )
            step_file = step_root / f'{len(entries):04d}.json'
            write_json(step_file, step, maximum_bytes=maximum_step_bytes,
                       label='step JSON')
            entries.append({'path': str(step_file.relative_to(root)),
                            'bytes': step_file.stat().st_size,
                            'sha256': file_sha256(step_file)})
            yield step
            del step

    full = root / 'repeat-0.json'
    with full.open('x', encoding='utf-8', newline='\n') as stream:
        writer = (ByteBoundedWriter(stream, maximum_full_bytes, 'full JSON')
                  if maximum_full_bytes is not None else stream)
        for chunk in iter_path_json(metadata, recorded_steps()):
            writer.write(chunk)
    meta_file = root / 'path-metadata.json'
    write_json(meta_file, metadata, maximum_bytes=MAX_METADATA_JSON_BYTES
               if maximum_full_bytes is not None else None, label='metadata JSON')
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
    require(type(value) is int and value in (256, 512, 1024, 2048, 4096),
            "predeclared research layer count must be 256, 512, 1024, 2048 or 4096")
    return value, value // 2


def protocol_record(layers, comparison_layers, source_count, config):
    return {
        "schema": f"fixed-planar-{layers}-refinement-protocol.v1",
        "source_revision": SOURCE_REVISION,
        "source_manifest_sha256": MANIFEST_SHA256,
        "source_files_git_verified": source_count,
        "input_sha256": INPUT_SHA256,
        "concrete_layer_count": layers,
        "comparison_layer_count": comparison_layers,
        "target_displacements_m": tuple(i / 500 for i in range(1, 41)),
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
    }


def preflight_output_format(layers, output_root):
    """Reserve enough free space for every file allowed by the bounded reader.

    This establishes destination capacity at preflight time, not the unknown
    serialized size of the future nonlinear path. Writer limits enforce that.
    """
    if layers != 4096:
        return
    required_bytes = (MAX_FULL_JSON_BYTES + 40 * MAX_STEP_JSON_BYTES
                      + MAX_METADATA_JSON_BYTES + OUTPUT_FORMAT_RESERVE_BYTES)
    try:
        available_bytes = shutil.disk_usage(output_root).free
    except OSError as error:
        raise ValueError('4096 output capacity unestablished: cannot measure free space') from error
    require(available_bytes >= required_bytes,
            f'4096 output capacity unestablished: {available_bytes} bytes free, '
            f'{required_bytes} bytes required for the bounded full JSON, forty '
            'step files, metadata and reserve')


def record_output_format_failure(root, *, layers, target_count, path, solve_wall_ns,
                                 through_failure_wall_ns, error):
    """Leave an incomplete packet with measured work and no published index."""
    full = root / 'repeat-0.json'
    step_files = list((root / 'steps').glob('*.json'))
    meta = root / 'path-metadata.json'
    full_bytes = full.stat().st_size if full.exists() else 0
    step_bytes = sum(file.stat().st_size for file in step_files)
    metadata_bytes = meta.stat().st_size if meta.exists() else 0
    require(not (root / 'path-index.json').exists(), 'incomplete packet has a path index')
    write_json(root / 'failure-summary.json', {
        'schema': 'fixed-planar-refinement-output-failure.v1',
        'status': 'incomplete',
        'reason_code': 'output_format_limit',
        'reason': str(error),
        'source_revision': SOURCE_REVISION,
        'concrete_layer_count': layers,
        'requested_targets': target_count,
        'attempted_targets': len(path.steps),
        'committed_steps': sum(step.committed for step in path.steps),
        'solver_status': path.status,
        'solver_contract_pass': path.contract_pass,
        'solve_wall_ns': solve_wall_ns,
        'through_failure_wall_ns': through_failure_wall_ns,
        'written_bytes': {
            'full_json': full_bytes,
            'step_json': step_bytes,
            'metadata_json': metadata_bytes,
            'total': full_bytes + step_bytes + metadata_bytes,
        },
        'path_index_published': False,
        'physical_validation': False,
        'public_result_authority': False,
    })


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
    write("protocol.json", protocol_record(layers, comparison_layers, len(files), config))
    if layers in PROTOCOL_SHA256:
        require(file_sha256(root / "protocol.json") == PROTOCOL_SHA256[layers],
                f"predeclared {layers}-layer protocol changed")
    try:
        preflight_output_format(layers, root)
    except ValueError as error:
        write('failure-summary.json', {
            'schema': 'fixed-planar-refinement-preflight-failure.v1',
            'status': 'incomplete',
            'reason_code': 'output_capacity_unestablished',
            'reason': str(error),
            'source_revision': SOURCE_REVISION,
            'concrete_layer_count': layers,
            'requested_targets': len(targets),
            'attempted_targets': 0,
            'solve_wall_ns': 0,
            'through_failure_wall_ns': perf_counter_ns() - process_started,
            'written_bytes': {'full_json': 0, 'step_json': 0, 'metadata_json': 0,
                              'total': 0},
            'path_index_published': False,
        })
        raise
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
    try:
        receipt = write_path_artifacts(
            root, metadata, (step.to_dict() for step in path.steps),
            maximum_full_bytes=MAX_FULL_JSON_BYTES if layers == 4096 else None,
            maximum_step_bytes=MAX_STEP_JSON_BYTES if layers == 4096 else None,
            maximum_steps=len(targets) if layers == 4096 else None,
        )
    except OutputFormatLimitError as error:
        record_output_format_failure(root, layers=layers, target_count=len(targets),
                                     path=path, solve_wall_ns=solve_ns,
                                     through_failure_wall_ns=perf_counter_ns()
                                     - process_started, error=error)
        raise
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
    parser.add_argument('--layers', type=int, choices=(256, 512, 1024, 2048, 4096), default=256)
    args = parser.parse_args()
    run(args.bundle, args.output_parent, Path(__file__).resolve().parents[1], layers=args.layers)
