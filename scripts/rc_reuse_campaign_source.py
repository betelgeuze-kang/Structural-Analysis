"""Exact-checkout source and dependency identity for an RC reuse campaign.

This is software provenance. It does not attest numerical or physical accuracy.
"""

import base64
from functools import lru_cache
import hashlib
from importlib import metadata
import os
from pathlib import Path
import platform
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
DEPENDENCIES = ("numpy", "scipy", "matplotlib", "jsonschema")
THREAD_ENVIRONMENT = (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "PYTHONHASHSEED",
)


def require_public_fixture(path):
    """Keep clean hosted runs confined to committed public example inputs."""
    resolved = path.resolve()
    if not resolved.is_file() or not resolved.is_relative_to(ROOT / "examples"):
        raise ValueError("clean-source campaign requires public example inputs")
    require_git_blob(resolved)


def _git(*args):
    return subprocess.check_output(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stderr=subprocess.PIPE,
    ).strip()


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_git_blob(path):
    """Check working bytes against HEAD even if Git index flags hide changes."""
    resolved = path.resolve()
    if not resolved.is_file() or not resolved.is_relative_to(ROOT):
        raise ValueError("campaign source file is outside checkout")
    relative = resolved.relative_to(ROOT).as_posix()
    try:
        if _git("ls-files", "--error-unmatch", "--", relative) != relative:
            raise ValueError("campaign source file is not tracked")
        committed = subprocess.check_output(
            ["git", "show", f"HEAD:{relative}"], cwd=ROOT, stderr=subprocess.PIPE
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError("campaign source file is not in HEAD") from exc
    if _sha256(resolved) != hashlib.sha256(committed).hexdigest():
        raise ValueError(f"campaign source differs from HEAD: {relative}")
    return relative


def _module_sources():
    sources = {}
    for name, module in sorted(sys.modules.items()):
        if not (
            name == "structural_analysis"
            or name.startswith("structural_analysis.")
            or name == "scripts"
            or name.startswith("scripts.")
        ):
            continue
        original = getattr(module, "__file__", None)
        if original is None:
            continue  # namespace packages have no executable file
        path = Path(original).resolve()
        if not path.is_file() or not path.is_relative_to(ROOT):
            raise ValueError(f"imported repository module outside checkout: {name}")
        relative = path.relative_to(ROOT).as_posix()
        if (
            not (
                relative.startswith("src/structural_analysis/")
                or relative.startswith("scripts/")
            )
            or path.suffix != ".py"
        ):
            raise ValueError(f"unexpected repository module source: {name}")
        require_git_blob(path)
        sources[name] = {"path": relative, "sha256": _sha256(path)}
    if "structural_analysis.api.nonlinear_fiber_frame" not in sources or (
        "scripts.diagnose_rc_control_line_search_reuse" not in sources
    ):
        raise ValueError(
            "required numerical modules were not imported from the checkout"
        )
    return sources


def _dependencies():
    result = {}
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name", "").lower().replace("_", "-")
        if not name:
            raise ValueError("installed dependency identity is missing")
        record = distribution.read_text("RECORD")
        item = {
            "version": distribution.version,
            "record_sha256": (
                hashlib.sha256(record.encode("utf-8")).hexdigest() if record else None
            ),
        }
        result.setdefault(name, [])
        if item not in result[name]:
            result[name].append(item)
    for name in DEPENDENCIES:
        if name not in result or not any(
            item["record_sha256"] is not None for item in result[name]
        ):
            raise ValueError(f"direct dependency RECORD unavailable: {name}")
    return {
        name: sorted(
            items, key=lambda item: (item["version"], item["record_sha256"] or "")
        )
        for name, items in sorted(result.items())
    }


@lru_cache(maxsize=len(DEPENDENCIES))
def _distribution_files(base):
    distribution = metadata.distribution(base)
    record = distribution.read_text("RECORD")
    files = distribution.files
    if not record or not files:
        raise ValueError(f"dependency file inventory unavailable: {base}")
    return (
        Path(distribution.locate_file("")).resolve(),
        distribution.version,
        hashlib.sha256(record.encode("utf-8")).hexdigest(),
        {entry.as_posix(): entry for entry in files},
    )


def _dependency_file_identity(base, path):
    root, version, record_sha256, files = _distribution_files(base)
    resolved = path.resolve()
    if not resolved.is_file() or not resolved.is_relative_to(root):
        raise ValueError(f"loaded dependency module outside its distribution: {base}")
    relative = resolved.relative_to(root).as_posix()
    entry = files.get(relative)
    if entry is None or entry.hash is None or entry.hash.mode != "sha256":
        raise ValueError(
            f"loaded dependency module has no distribution hash: {relative}"
        )
    digest = hashlib.sha256(resolved.read_bytes()).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    if entry.hash.value != encoded:
        raise ValueError(f"loaded dependency module differs from RECORD: {relative}")
    return {
        "distribution": base,
        "distribution_version": version,
        "record_sha256": record_sha256,
        "path": relative,
        "sha256": digest.hex(),
    }


def _dependency_modules():
    result = {}
    for name, module in sorted(sys.modules.items()):
        base = name.split(".", 1)[0]
        if base not in DEPENDENCIES:
            continue
        original = getattr(module, "__file__", None)
        if original is None:
            continue
        result[name] = _dependency_file_identity(base, Path(original))
    return result


def snapshot_clean_source():
    """Reject local modifications and record the actual imported source/deps."""
    if Path(_git("rev-parse", "--show-toplevel")).resolve() != ROOT:
        raise ValueError("campaign source is not the expected checkout")
    revision = _git("rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("campaign source revision is invalid")
    if _git("status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("campaign source checkout must be clean")
    for script in (
        "scripts/run_rc_reuse_campaign.py",
        "scripts/audit_rc_reuse_campaign_packet.py",
    ):
        require_git_blob(ROOT / script)
    return {
        "schema": "rc-reuse-clean-source.v1",
        "source_revision": revision,
        "checkout_clean": True,
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "thread_environment": {key: os.environ.get(key) for key in THREAD_ENVIRONMENT},
        "dependencies": _dependencies(),
        "imported_dependency_modules": _dependency_modules(),
        "imported_repository_modules": _module_sources(),
    }


def verify_saved_source(value):
    """Compare a saved run identity with a separate clean audit process."""
    if (
        type(value) is not dict
        or set(value) != {"schema", "before", "after"}
        or (value["schema"] != "rc-reuse-execution-source.v1")
    ):
        raise ValueError("invalid campaign execution source receipt")
    before, after = value["before"], value["after"]
    current = snapshot_clean_source()
    expected = {
        "schema",
        "source_revision",
        "checkout_clean",
        "python",
        "thread_environment",
        "dependencies",
        "imported_dependency_modules",
        "imported_repository_modules",
    }
    for label, saved in (("before", before), ("after", after)):
        if (
            type(saved) is not dict
            or set(saved) != expected
            or (
                saved["schema"] != current["schema"]
                or saved["source_revision"] != current["source_revision"]
                or saved["checkout_clean"] is not True
                or saved["python"] != current["python"]
                or saved["thread_environment"] != current["thread_environment"]
                or saved["dependencies"] != current["dependencies"]
            )
        ):
            raise ValueError(f"campaign {label} source or dependency mismatch")
        modules = saved["imported_repository_modules"]
        if type(modules) is not dict or not modules:
            raise ValueError(f"campaign {label} module inventory is empty")
        if not {
            "structural_analysis.api.nonlinear_fiber_frame",
            "scripts.diagnose_rc_control_line_search_reuse",
        }.issubset(modules):
            raise ValueError(f"campaign {label} numerical modules are missing")
        for name, item in modules.items():
            if (
                type(name) is not str
                or type(item) is not dict
                or set(item) != {"path", "sha256"}
                or type(item["path"]) is not str
                or type(item["sha256"]) is not str
            ):
                raise ValueError(f"campaign {label} module inventory is malformed")
            path = (ROOT / item["path"]).resolve()
            if (
                not path.is_relative_to(ROOT)
                or not path.is_file()
                or (_sha256(path) != item["sha256"])
            ):
                raise ValueError(f"campaign {label} module bytes mismatch: {name}")
        dependency_modules = saved["imported_dependency_modules"]
        if type(dependency_modules) is not dict:
            raise ValueError(f"campaign {label} dependency modules are malformed")
        for name, item in dependency_modules.items():
            base = name.split(".", 1)[0]
            if (
                base not in DEPENDENCIES
                or type(item) is not dict
                or set(item)
                != {
                    "distribution",
                    "distribution_version",
                    "record_sha256",
                    "path",
                    "sha256",
                }
                or item["distribution"] != base
                or type(item["path"]) is not str
                or (type(item["sha256"]) is not str)
            ):
                raise ValueError(
                    f"campaign {label} dependency module malformed: {name}"
                )
            root = _distribution_files(base)[0]
            path = (root / item["path"]).resolve()
            if not path.is_relative_to(root) or (
                _dependency_file_identity(base, path) != item
            ):
                raise ValueError(
                    f"campaign {label} dependency module bytes mismatch: {name}"
                )
    if not set(before["imported_repository_modules"]).issubset(
        after["imported_repository_modules"]
    ):
        raise ValueError("campaign imported module inventory lost entries")
    for name, item in before["imported_repository_modules"].items():
        if item != after["imported_repository_modules"][name]:
            raise ValueError(
                f"campaign imported module changed during execution: {name}"
            )
    if not set(before["imported_dependency_modules"]).issubset(
        after["imported_dependency_modules"]
    ):
        raise ValueError("campaign dependency module inventory lost entries")
    for name, item in before["imported_dependency_modules"].items():
        if item != after["imported_dependency_modules"][name]:
            raise ValueError(
                f"campaign dependency module changed during execution: {name}"
            )
    return current["source_revision"]
