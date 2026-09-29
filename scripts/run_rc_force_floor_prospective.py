"""Run a committed RC force-floor protocol from an exact clean source checkout.

The protocol and all four input blobs must already exist at the supplied
ancestor commit. The packet plan is saved before search or numerical work.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory


PROTOCOL_SCHEMA = "experimental-rc-control-force-floor-protocol.v1"
PLAN_SCHEMA = "experimental-rc-control-force-floor-predeclaration.v1"
RUNNER_SCHEMA = "experimental-rc-control-force-floor-runner-receipt.v1"
INVENTORY_SCHEMA = "experimental-rc-control-force-floor-packet-inventory.v1"
SEARCH_PLAN_SCHEMA = "experimental-rc-control-force-floor-price-search-plan.v1"
SEARCH_REPORT_SCHEMA = "experimental-rc-control-force-floor-price-search.v1"
ROLES = ("model", "request", "experiment", "floor_plan")
MAX_BYTES = {
    "protocol": 1024 * 1024,
    "model": 16 * 1024 * 1024,
    "request": 128 * 1024,
    "experiment": 1024 * 1024,
    "floor_plan": 128 * 1024,
}
HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
REVISION = re.compile(r"[0-9a-f]{40}\Z")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _strict_object(raw: bytes, name: str, maximum: int) -> dict:
    if len(raw) > maximum:
        raise ValueError(f"{name} exceeds the JSON byte bound")

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key in {name}: {key}")
            value[key] = item
        return value

    def nonfinite(value):
        raise ValueError(f"nonfinite JSON token in {name}: {value}")

    result = json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)
    if type(result) is not dict:
        raise ValueError(f"{name} must be a JSON object")
    return result


def _read(path: Path, maximum: int) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError(f"input exceeds byte bound: {path}")
    return raw


def _write_json(path: Path, value: dict) -> None:
    with path.open("xb") as stream:
        stream.write(_canonical(value) + b"\n")


def _git(repo: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", *arguments], cwd=repo, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        raise ValueError(f"git command failed: {arguments[0]}")
    return result.stdout.strip() if arguments[0] in ("rev-parse", "cat-file") else result.stdout


def _committed_blob(repo: Path, revision: str, relative: str, maximum: int) -> bytes:
    object_name = f"{revision}:{relative}"
    if _git(repo, "cat-file", "-t", object_name) != b"blob":
        raise ValueError(f"committed input is not a blob: {relative}")
    size = int(_git(repo, "cat-file", "-s", object_name))
    if size > maximum:
        raise ValueError(f"committed input exceeds byte bound: {relative}")
    raw = _git(repo, "show", object_name)
    if len(raw) != size:
        raise ValueError(f"committed input byte length differs: {relative}")
    return raw


def _source_file(repo: Path, relative: str) -> Path:
    if (
        type(relative) is not str or not relative.startswith("examples/research/")
        or "\\" in relative or Path(relative).is_absolute()
        or ".." in Path(relative).parts or "." in Path(relative).parts
        or Path(relative).as_posix() != relative
    ):
        raise ValueError("source path must be repo-relative under examples/research/")
    path = repo / relative
    current = repo
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("source path contains a symlink")
    if not path.is_file() or not path.resolve().is_relative_to(repo.resolve()):
        raise ValueError(f"source file is unavailable: {relative}")
    return path


def _protocol_relative(repo: Path, argument: Path) -> str:
    if ".." in argument.parts:
        raise ValueError("protocol path traversal is not allowed")
    path = argument if argument.is_absolute() else repo / argument
    try:
        relative = path.relative_to(repo).as_posix()
    except ValueError as error:
        raise ValueError("protocol must be inside the source checkout") from error
    _source_file(repo, relative)
    return relative


def preflight_protocol(
    repo: Path, protocol_path: Path, protocol_commit: str, output: Path,
) -> dict:
    """Verify source, ancestor protocol, and every input before creating output."""
    repo = repo.resolve()
    output = output.resolve()
    if output == repo or output.is_relative_to(repo):
        raise ValueError("packet output must be outside the source checkout")
    if type(protocol_commit) is not str or REVISION.fullmatch(protocol_commit) is None:
        raise ValueError("40-character protocol commit required")
    if Path(_git(repo, "rev-parse", "--show-toplevel").decode()).resolve() != repo:
        raise ValueError("source path must be the Git checkout root")
    head = _git(repo, "rev-parse", "HEAD").decode()
    if REVISION.fullmatch(head) is None:
        raise ValueError("exact source HEAD required")
    if _git(repo, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("prospective run requires an exact clean source checkout")
    if _git(repo, "cat-file", "-t", protocol_commit) != b"commit":
        raise ValueError("protocol revision must be a commit")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", protocol_commit, head],
        cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if ancestor.returncode:
        raise ValueError("protocol commit is not an ancestor of source HEAD")
    relative = _protocol_relative(repo, protocol_path)
    working = _read(_source_file(repo, relative), MAX_BYTES["protocol"])
    frozen = _committed_blob(repo, protocol_commit, relative, MAX_BYTES["protocol"])
    if working != frozen:
        raise ValueError("protocol bytes differ from committed protocol")
    protocol = _strict_object(working, "protocol", MAX_BYTES["protocol"])
    if set(protocol) != {
        "schema_version", "inputs", "full_analysis_budget", "reuse_line_search_assembly"
    } or protocol["schema_version"] != PROTOCOL_SCHEMA:
        raise ValueError("exact prospective protocol fields required")
    inputs = protocol["inputs"]
    if type(inputs) is not dict or set(inputs) != set(ROLES):
        raise ValueError("exact protocol input roles required")
    budget = protocol["full_analysis_budget"]
    if type(budget) is not int or not 2 <= budget <= 17:
        raise ValueError("bounded analysis budget required")
    if type(protocol["reuse_line_search_assembly"]) is not bool:
        raise ValueError("explicit line-search reuse boolean required")
    paths, digests, blobs = {}, {}, {}
    for role in ROLES:
        reference = inputs[role]
        if type(reference) is not dict or set(reference) != {"path", "sha256"}:
            raise ValueError(f"exact {role} input reference required")
        relative_input = reference["path"]
        expected = reference["sha256"]
        if type(expected) is not str or HASH.fullmatch(expected) is None:
            raise ValueError(f"valid {role} input SHA256 required")
        working_input = _read(_source_file(repo, relative_input), MAX_BYTES[role])
        committed_input = _committed_blob(
            repo, protocol_commit, relative_input, MAX_BYTES[role]
        )
        if working_input != committed_input or _sha(working_input) != expected:
            raise ValueError(f"{role} input differs from committed protocol")
        paths[role] = relative_input
        digests[role] = expected
        blobs[role] = working_input
    runner_relative = "scripts/run_rc_force_floor_prospective.py"
    runner_raw = _read(repo / runner_relative, 1024 * 1024)
    if runner_raw != _committed_blob(repo, head, runner_relative, 1024 * 1024):
        raise ValueError("runner source differs from exact HEAD")
    return {
        "repo": repo,
        "output": output,
        "source_revision": head,
        "protocol_commit": protocol_commit,
        "protocol_path": relative,
        "protocol_sha256": _sha(working),
        "input_paths": paths,
        "input_sha256": digests,
        "input_blobs": blobs,
        "full_analysis_budget": budget,
        "reuse_line_search_assembly": protocol["reuse_line_search_assembly"],
        "runner_sha256": _sha(runner_raw),
    }


def _decoded_inputs(frozen: dict) -> dict:
    """Parse pinned blobs and reject invalid study inputs before packet creation."""
    from structural_analysis.api.rc_fiber_frame_direct_control_request import (
        decode_bounded_rc_fiber_direct_control_request,
    )
    from structural_analysis.benchmark.fiber_frame_design_cli import (
        read_design_experiment_with_material_history,
    )
    from structural_analysis.benchmark.rc_control_force_floor_cli import (
        read_force_response_floor,
    )
    from structural_analysis.io.neutral.loader import load_neutral_json_bytes

    paths = frozen["input_paths"]
    model = load_neutral_json_bytes(
        frozen["input_blobs"]["model"], source_path=paths["model"]
    )
    request = decode_bounded_rc_fiber_direct_control_request(
        frozen["input_blobs"]["request"]
    )
    # Path-based readers consume copies of the pinned bytes, never a file that
    # could change in the checkout between preflight and parsing.
    with TemporaryDirectory(prefix="rc-force-floor-inputs-") as directory:
        temporary = Path(directory)
        experiment = temporary / "experiment.json"
        floor_plan = temporary / "floor_plan.json"
        experiment.write_bytes(frozen["input_blobs"]["experiment"])
        floor_plan.write_bytes(frozen["input_blobs"]["floor_plan"])
        candidates, prices, terminal, history, material = (
            read_design_experiment_with_material_history(experiment)
        )
        floor = read_force_response_floor(floor_plan)
    if prices is None or history is None or material is None:
        raise ValueError("floor search requires prices, history and material limits")
    if frozen["full_analysis_budget"] >= len(candidates) + 1:
        raise ValueError("online budget must be smaller than the full pool")
    return {
        "baseline": model,
        "candidates": candidates,
        "request": request,
        "force_response_floor": floor,
        "history_limits": history,
        "material_limits": material,
        "terminal_limits": terminal,
        "prices": prices,
    }


def _require_runtime_source(repo: Path) -> None:
    """Load the solver package from this checkout, never an ambient install."""
    package_root = (repo / "src" / "structural_analysis").resolve()
    if not package_root.is_dir():
        raise ValueError("source checkout lacks the structural_analysis package")
    sys.path.insert(0, str(repo / "src"))
    importlib.import_module("structural_analysis")
    for name, module in tuple(sys.modules.items()):
        if name != "structural_analysis" and not name.startswith("structural_analysis."):
            continue
        origin = getattr(module, "__file__", None)
        if origin is None or not Path(origin).resolve().is_relative_to(package_root):
            raise ValueError(f"runtime package came from another checkout: {name}")


def _execute_search(study_inputs: dict, frozen: dict, binding: dict) -> dict:
    from structural_analysis.benchmark.rc_control_force_floor_search import (
        compare_rc_control_force_floor_price_search,
    )

    return compare_rc_control_force_floor_price_search(
        **study_inputs,
        source_revision=frozen["source_revision"],
        output_directory=frozen["output"] / "search",
        full_analysis_budget=frozen["full_analysis_budget"],
        reuse_line_search_assembly=frozen["reuse_line_search_assembly"],
        protocol_binding=binding,
    )


def _assert_source_unchanged(frozen: dict) -> None:
    repo = frozen["repo"]
    if (
        _git(repo, "rev-parse", "HEAD").decode() != frozen["source_revision"]
        or _git(repo, "status", "--porcelain", "--untracked-files=all")
    ):
        raise ValueError("source checkout changed during prospective search")


def _checked_search(frozen: dict, binding: dict, returned: dict) -> tuple[dict, dict, str, str]:
    search = frozen["output"] / "search"
    plan_raw = _read(search / "plan.json", 16 * 1024 * 1024)
    result_raw = _read(search / "result.json", 16 * 1024 * 1024)
    plan = _strict_object(plan_raw, "search plan", 16 * 1024 * 1024)
    result = _strict_object(result_raw, "search result", 16 * 1024 * 1024)
    if (
        plan.get("schema_version") != SEARCH_PLAN_SCHEMA
        or result.get("schema_version") != SEARCH_REPORT_SCHEMA
        or plan.get("source_revision") != frozen["source_revision"]
        or result.get("source_revision") != frozen["source_revision"]
        or plan.get("protocol_binding") != binding
        or plan.get("plan_hash") != _sha(_canonical({
            key: value for key, value in plan.items() if key != "plan_hash"
        }))
        or result.get("plan_hash") != plan["plan_hash"]
        or result.get("report_hash") != _sha(_canonical({
            key: value for key, value in result.items() if key != "report_hash"
        }))
        or _canonical(returned) != _canonical(result)
        or plan.get("learned_policy_used") is not False
        or result.get("claims", {}).get("learned_policy_used") is not False
        or result.get("claims", {}).get("independent_physical_validation") is not False
        or result.get("claims", {}).get("net_ai_savings_proved") is not False
        or result.get("claims", {}).get("confirmed_currency_savings") is not False
    ):
        raise ValueError("saved search differs from frozen source/protocol binding")
    return plan, result, _sha(plan_raw), _sha(result_raw)


def _inventory(packet: Path) -> dict:
    files = []
    for path in packet.rglob("*"):
        if path.is_symlink():
            raise ValueError("packet contains a symlink")
        if path.is_file() and path.relative_to(packet).as_posix() not in (
            "inventory.json", "audit.json"
        ):
            raw = path.read_bytes()
            files.append([path.relative_to(packet).as_posix(), len(raw), _sha(raw)])
    files.sort(key=lambda row: row[0])
    return {
        "schema_version": INVENTORY_SCHEMA,
        "files": files,
        "inventory_sha256": _sha(_canonical(files)),
    }


def run_packet(repo: Path, protocol_path: Path, protocol_commit: str, output: Path) -> dict:
    frozen = preflight_protocol(repo, protocol_path, protocol_commit, output)
    _require_runtime_source(frozen["repo"])
    study_inputs = _decoded_inputs(frozen)
    packet = frozen["output"]
    packet.mkdir(parents=True, exist_ok=False)
    inputs = packet / "inputs"
    inputs.mkdir()
    for role in ROLES:
        with (inputs / f"{role}.json").open("xb") as stream:
            stream.write(frozen["input_blobs"][role])
    binding = {
        "protocol_commit": frozen["protocol_commit"],
        "protocol_path": frozen["protocol_path"],
        "protocol_sha256": frozen["protocol_sha256"],
        "input_sha256": frozen["input_sha256"],
    }
    plan = {
        "schema_version": PLAN_SCHEMA,
        "source_revision": frozen["source_revision"],
        "source_checkout_clean": True,
        "protocol_commit": frozen["protocol_commit"],
        "protocol_path": frozen["protocol_path"],
        "protocol_sha256": frozen["protocol_sha256"],
        "input_paths": frozen["input_paths"],
        "input_sha256": frozen["input_sha256"],
        "full_analysis_budget": frozen["full_analysis_budget"],
        "reuse_line_search_assembly": frozen["reuse_line_search_assembly"],
        "search_mode": "price_order_then_exhaustive_oracle",
        "runner_sha256": frozen["runner_sha256"],
    }
    plan["plan_hash"] = _sha(_canonical(plan))
    _write_json(packet / "plan.json", plan)
    returned = _execute_search(study_inputs, frozen, binding)
    _assert_source_unchanged(frozen)
    search_plan, result, search_plan_sha, search_report_sha = _checked_search(
        frozen, binding, returned
    )
    receipt = {
        "schema_version": RUNNER_SCHEMA,
        "source_revision": frozen["source_revision"],
        "clean_source_checkout": True,
        "protocol_commit": frozen["protocol_commit"],
        "protocol_path": frozen["protocol_path"],
        "protocol_sha256": frozen["protocol_sha256"],
        "input_paths": frozen["input_paths"],
        "input_sha256": frozen["input_sha256"],
        "full_analysis_budget": frozen["full_analysis_budget"],
        "reuse_line_search_assembly": frozen["reuse_line_search_assembly"],
        "outer_plan_hash": plan["plan_hash"],
        "outer_plan_sha256": _sha((packet / "plan.json").read_bytes()),
        "search_plan_hash": search_plan["plan_hash"],
        "search_plan_sha256": search_plan_sha,
        "search_report_hash": result["report_hash"],
        "search_report_sha256": search_report_sha,
        "runner_sha256": frozen["runner_sha256"],
        "independent_physical_validation": False,
        "learned_policy_used": False,
        "ai_benefit_claimed": False,
    }
    receipt["report_hash"] = _sha(_canonical(receipt))
    _write_json(packet / "runner.json", receipt)
    _write_json(packet / "inventory.json", _inventory(packet))
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--protocol-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    receipt = run_packet(repo, args.protocol, args.protocol_commit, args.output)
    print(json.dumps({
        "source_revision": receipt["source_revision"],
        "protocol_sha256": receipt["protocol_sha256"],
        "search_report_hash": receipt["search_report_hash"],
        "report_hash": receipt["report_hash"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
