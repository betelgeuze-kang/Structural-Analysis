from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


adapter = _load(
    "build_planar_workbench_case_canonicalization_test",
    "scripts/build_planar_workbench_case.py",
)
runner = _load(
    "run_planar_product_replay_canonicalization_test",
    "scripts/run_planar_product_replay.py",
)


def _write(path: Path, payload: object) -> None:
    path.write_bytes((json.dumps(payload, sort_keys=True) + "\n").encode("utf-8"))


def _artifacts(tmp_path: Path) -> tuple[Path, Path, Path]:
    model = tmp_path / "model.json"
    result = tmp_path / "result.json"
    report = tmp_path / "report.json"
    _write(model, {"capability_profile": adapter.PROFILE, "nodes": [], "elements": []})
    _write(
        result,
        {
            "profile": adapter.PROFILE,
            "status": "converged",
            "converged": True,
            "result_hash": "sha256:" + "1" * 64,
            "result_ir": {},
        },
    )
    _write(
        report,
        {
            "artifact_contract_pass": True,
            "execution_contract_pass": True,
        },
    )
    return model, result, report


def test_replay_json_writers_emit_lf_bytes_without_platform_translation(
    tmp_path: Path,
) -> None:
    payload = {"value": "line\ninside"}
    for index, writer in enumerate((adapter._write_json, runner._write_json)):
        path = tmp_path / f"writer-{index}.json"
        writer(path, payload)
        raw = path.read_bytes()
        assert b"\r\n" not in raw
        assert raw.endswith(b"\n")
        assert json.loads(raw) == payload


def test_workbench_projection_accepts_only_canonical_relative_source_path(
    tmp_path: Path,
) -> None:
    model, result, report = _artifacts(tmp_path)
    case = adapter.build_workbench_case(
        model_path=model,
        result_path=result,
        report_path=report,
        source_commit_sha="a" * 40,
        engine_version="structural-analysis@0.3.0",
        generated_at="2026-08-05T00:00:00Z",
        source_path=runner.CANONICAL_MODEL_SOURCE_PATH,
    )

    assert case["provenance"]["sourcePath"] == "product-replay/public-model.json"

    for invalid in (
        "/absolute/model.json",
        "C:/absolute/model.json",
        "product-replay\\public-model.json",
        "product-replay/../public-model.json",
    ):
        with pytest.raises(
            adapter.PlanarWorkbenchProjectionError,
            match="source_path_not_canonical_relative",
        ):
            adapter.build_workbench_case(
                model_path=model,
                result_path=result,
                report_path=report,
                source_commit_sha="a" * 40,
                engine_version="structural-analysis@0.3.0",
                generated_at="2026-08-05T00:00:00Z",
                source_path=invalid,
            )
