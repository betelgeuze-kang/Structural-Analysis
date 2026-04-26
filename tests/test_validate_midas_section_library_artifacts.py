from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[1] / "implementation/phase1/validate_midas_section_library_artifacts.py"
    spec = importlib.util.spec_from_file_location("validate_midas_section_library_artifacts_for_tests", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_validate_midas_section_library_artifacts_cli(tmp_path: Path, monkeypatch, capsys) -> None:
    module = _load_module()
    artifacts: list[Path] = []

    for index, (coverage, used, templates, source) in enumerate(
        [
            (183, 182, 183, "midas_parser_derived"),
            (183, 181, 182, "viewer fallback derived"),
            (183, 182, 183, "parser_additive_metadata"),
        ],
        start=1,
    ):
        model_path = tmp_path / f"model_{index}.json"
        _write_json(
            model_path,
            {
                "model": {
                    "metadata": {
                        "section_library": {
                            "provenance": "parser_additive_metadata",
                            "derived_catalog": {"source_label": source, "templates": [{}] * templates},
                            "summary": {
                                "section_row_count": coverage,
                                "used_section_count": used,
                                "derived_template_count": templates,
                            },
                        }
                    }
                }
            },
        )
        artifacts.append(model_path)

    monkeypatch.setattr(module, "DEFAULT_TARGETS", tuple(artifacts))

    exit_code = module.main([])
    captured = capsys.readouterr().out.strip().splitlines()

    assert exit_code == 0
    assert len(captured) == 3
    assert captured[0].startswith("MIDAS section-library: ok")
    assert "182/183 used" in captured[0]
    assert "183 templates" in captured[0]
    assert "source=midas_parser_derived" in captured[0]
    assert str(artifacts[0]) in captured[0]
    assert captured[1].startswith("MIDAS section-library: ok")
    assert "181/183 used" in captured[1]
    assert "182 templates" in captured[1]
    assert "source=viewer fallback derived" in captured[1]
    assert str(artifacts[1]) in captured[1]
    assert captured[2].startswith("MIDAS section-library: ok")
    assert "182/183 used" in captured[2]
    assert "183 templates" in captured[2]
    assert "source=parser_additive_metadata" in captured[2]
    assert str(artifacts[2]) in captured[2]


def test_validate_midas_section_library_artifacts_detects_missing_metadata(tmp_path: Path, monkeypatch, capsys) -> None:
    module = _load_module()
    model_path = tmp_path / "model.json"
    _write_json(model_path, {"model": {"metadata": {}}})

    monkeypatch.setattr(module, "DEFAULT_TARGETS", (model_path,))

    exit_code = module.main(["--require"])
    captured = capsys.readouterr().out.strip()

    assert exit_code == 1
    assert captured.startswith("MIDAS section-library: missing")
    assert "source=n/a" in captured
    assert str(model_path) in captured
