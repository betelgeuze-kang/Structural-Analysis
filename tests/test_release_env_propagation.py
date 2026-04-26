from __future__ import annotations

import json
from pathlib import Path

from implementation.phase1 import run_p0_core_gap_pipeline as p0_pipe
from implementation.phase1 import run_phase1_topk_pipeline as topk_pipe
from implementation.phase1 import run_phase3_megastructure_pipeline as phase3_pipe


class _DummyProc:
    def __init__(self) -> None:
        self.returncode = 0
        self.stdout = ""
        self.stderr = ""


def test_phase3_run_inherits_env_overrides(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_run(cmd, text, capture_output, env):  # noqa: ANN001
        captured.update(env)
        return _DummyProc()

    monkeypatch.setattr(phase3_pipe.subprocess, "run", fake_run)
    phase3_pipe.RUN_ENV_OVERRIDES.clear()
    phase3_pipe.RUN_ENV_OVERRIDES["PHASE1_DISABLE_CPU_FALLBACK"] = "1"
    logs: list[dict] = []
    assert phase3_pipe._run("x", ["python3", "-V"], logs) is True
    assert captured["PHASE1_DISABLE_CPU_FALLBACK"] == "1"


def test_topk_run_step_inherits_env_overrides(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_run(cmd, check, env):  # noqa: ANN001
        captured.update(env)
        return _DummyProc()

    monkeypatch.setattr(topk_pipe.subprocess, "run", fake_run)
    topk_pipe.RUN_ENV_OVERRIDES.clear()
    topk_pipe.RUN_ENV_OVERRIDES["PHASE1_GPU_PREPROCESS"] = "1"
    steps: list[dict] = []
    topk_pipe._run_step("x", ["python3", "-V"], steps)
    assert captured["PHASE1_GPU_PREPROCESS"] == "1"


def test_p0_run_inherits_env_overrides(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_run(cmd, capture_output, text, check, env):  # noqa: ANN001
        captured.update(env)
        return _DummyProc()

    monkeypatch.setattr(p0_pipe.subprocess, "run", fake_run)
    p0_pipe.RUN_ENV_OVERRIDES.clear()
    p0_pipe.RUN_ENV_OVERRIDES["PHASE1_DISABLE_CPU_FALLBACK"] = "1"
    ok, _, _, _ = p0_pipe._run(["python3", "-V"])
    assert ok is True
    assert captured["PHASE1_DISABLE_CPU_FALLBACK"] == "1"


def test_topk_phase1_ci_gate_command_includes_explicit_midas_section_artifacts(tmp_path: Path, monkeypatch) -> None:
    hf_csv = tmp_path / "hf.csv"
    lf_csv = tmp_path / "lf.csv"
    hf_csv.write_text("id,value\n1,1.0\n", encoding="utf-8")
    lf_csv.write_text("id,value\n1,1.0\n", encoding="utf-8")
    out_manifest = tmp_path / "pipeline_manifest.json"
    out_lock = tmp_path / "pipeline_config.lock.json"
    captured_cmds: dict[str, list[str]] = {}

    def fake_run_step(step_name, cmd, steps):  # noqa: ANN001
        captured_cmds[step_name] = list(cmd)
        steps.append({"step": step_name, "command": " ".join(cmd)})

    monkeypatch.setattr(topk_pipe, "_run_step", fake_run_step)
    monkeypatch.setattr(
        topk_pipe.argparse.ArgumentParser,
        "parse_args",
        lambda self: topk_pipe.argparse.Namespace(
            config=None,
            out_manifest=str(out_manifest),
            out_config_lock=str(out_lock),
            hf_csv=str(hf_csv),
            lf_csv=str(lf_csv),
            merged_csv=None,
            metric_source=None,
            artifact_label=None,
        ),
    )

    topk_pipe.main()

    ci_cmd = captured_cmds["phase1_ci_gate"]
    pairs = [
        (ci_cmd[index], ci_cmd[index + 1])
        for index in range(len(ci_cmd) - 1)
        if ci_cmd[index] == "--midas-section-library-artifact"
    ]
    assert pairs == [
        ("--midas-section-library-artifact", "implementation/phase1/open_data/midas/midas_generator_33.json"),
        ("--midas-section-library-artifact", "implementation/phase1/open_data/midas/midas_generator_33.pr_recheck.json"),
        ("--midas-section-library-artifact", "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"),
    ]
    manifest = json.loads(out_manifest.read_text(encoding="utf-8"))
    manifest_ci_step = next(step for step in manifest["steps"] if step["step"] == "phase1_ci_gate")
    assert "--midas-section-library-artifact implementation/phase1/open_data/midas/midas_generator_33.json" in manifest_ci_step["command"]
