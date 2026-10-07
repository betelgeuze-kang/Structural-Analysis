#!/usr/bin/env python3
"""Build an exact-byte standalone adapter for the isolated guardian loader.

Generated code embeds the reviewed source bytes instead of importing a mutable
checkout or an installed structural_analysis package at execution time.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

MODULES = (
    "rc_resource_boundary",
    "rc_cgroup_observer",
    "rc_cgroup_allocation",
    "rc_cgroup_guardian",
)


def build_adapter_source(root: Path) -> bytes:
    directory = root / "src" / "structural_analysis" / "execution"
    sources = {name: (directory / f"{name}.py").read_bytes() for name in MODULES}
    pins = {
        name: hashlib.sha256(source).hexdigest() for name, source in sources.items()
    }
    code = """# Generated exact-byte cgroup adapter; not an admission or enforcement receipt.
import hashlib
import sys
import types
import uuid
"""
    code += f"SOURCE_BYTES = {sources!r}\nSOURCE_SHA256 = {pins!r}\n"
    code += """
def prepare_boundary(plan):
    prefix = "_owned_rc_boundary_" + uuid.uuid4().hex
    if any(name == prefix or name.startswith(prefix + ".") for name in sys.modules):
        raise RuntimeError("private adapter module namespace collision")
    owned = []
    try:
        package = types.ModuleType(prefix)
        package.__path__ = []
        package.__package__ = prefix
        sys.modules[prefix] = package
        owned.append((prefix, package))
        for name, source in SOURCE_BYTES.items():
            if hashlib.sha256(source).hexdigest() != SOURCE_SHA256[name]:
                raise ValueError("embedded boundary source digest mismatch")
            full_name = prefix + "." + name
            module = types.ModuleType(full_name)
            module.__package__ = prefix
            module.__file__ = "<embedded:" + name + ">"
            sys.modules[full_name] = module
            owned.append((full_name, module))
            exec(compile(source, module.__file__, "exec"), module.__dict__)
        # The binding retains its function globals and owned descriptors. No
        # later call imports the private package or resolves checkout files.
        return owned[-1][1].prepare_boundary(plan)
    finally:
        for name, module in reversed(owned):
            if sys.modules.get(name) is module:
                del sys.modules[name]
"""
    return code.encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = build_adapter_source(args.repo_root)
    with args.output.open("xb") as stream:
        stream.write(source)


if __name__ == "__main__":
    main()
