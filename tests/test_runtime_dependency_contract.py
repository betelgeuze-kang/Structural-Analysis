from __future__ import annotations

import ast
import configparser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REQUIRED_RUNTIME_DEPENDENCIES = {
    "jsonschema>=4.20",
    "matplotlib>=3.7",
    "numpy>=1.23",
    "scipy>=1.10",
}


def _parse_pyproject_dependency_array(project_section: str) -> list[str]:
    lines = project_section.splitlines()
    dependency_expression: list[str] = []
    dependencies: object | None = None

    for line_number, line in enumerate(lines):
        key, separator, value = line.partition("=")
        if separator and key.strip() == "dependencies":
            dependency_expression.append(value)
            for continuation in lines[line_number + 1 :]:
                try:
                    dependencies = ast.literal_eval("\n".join(dependency_expression))
                except (SyntaxError, ValueError):
                    dependency_expression.append(continuation)
                    continue
                break
            else:
                dependencies = ast.literal_eval("\n".join(dependency_expression))
            break

    assert dependencies is not None, "pyproject.toml [project].dependencies is missing"
    assert isinstance(dependencies, list)
    return [str(spec).strip() for spec in dependencies]


def _pyproject_dependencies() -> set[str]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project_section = text.split("[project]", maxsplit=1)[1].split("\n[", maxsplit=1)[0]
    return set(_parse_pyproject_dependency_array(project_section))


def _setup_cfg_dependencies() -> set[str]:
    config = configparser.ConfigParser(interpolation=None)
    config.read(ROOT / "setup.cfg", encoding="utf-8")
    return {
        spec.strip()
        for spec in config.get("options", "install_requires").splitlines()
        if spec.strip()
    }


def _requirements_dependencies() -> set[str]:
    return {
        line.strip()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_pyproject_dependency_parser_preserves_pep_508_extras() -> None:
    section = 'dependencies = [\n  "requests[socks]>=2",\n]\n'

    assert _parse_pyproject_dependency_array(section) == ["requests[socks]>=2"]


def test_required_runtime_dependencies_match_across_package_metadata() -> None:
    dependencies_by_source = {
        "pyproject.toml": _pyproject_dependencies(),
        "setup.cfg": _setup_cfg_dependencies(),
        "requirements.txt": _requirements_dependencies(),
    }

    assert dependencies_by_source == {
        source: EXPECTED_REQUIRED_RUNTIME_DEPENDENCIES for source in dependencies_by_source
    }
