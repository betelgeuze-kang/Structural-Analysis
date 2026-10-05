from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import struct
from pathlib import Path

import pytest

from structural_analysis.api import _output_integrity
from structural_analysis.api import (
    PublicRCFiberFrameConfig,
    analyze_public_rc_fiber_frame,
    validate_public_rc_fiber_frame_result,
)
from structural_analysis.api import nonlinear_fiber_frame_cli
from structural_analysis.api import nonlinear_fiber_frame
from structural_analysis.io.neutral.loader import (
    load_neutral_json,
    load_neutral_json_bytes,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _payload() -> dict:
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {
            "axis_order": ["X", "Y", "Z"],
            "up_axis": "Z",
        },
        "nodes": [
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "N2", "coordinates": [3.0, 0.0, 0.0]},
        ],
        "elements": [
            {
                "id": "M1",
                "type": "stateful_rc_fiber_frame2d",
                "nodes": ["N1", "N2"],
                "section": "RC1",
                "integration_order": 2,
            }
        ],
        "materials": [
            {
                "id": "steel",
                "type": "bilinear_combined_hardening_steel",
                "elastic_modulus_mpa": 200_000.0,
                "yield_stress_mpa": 250.0,
                "isotropic_hardening_modulus_mpa": 3_000.0,
                "kinematic_hardening_modulus_mpa": 5_000.0,
                "yield_tolerance_mpa": 1.0e-10,
            },
            {
                "id": "concrete",
                "type": "asymmetric_concrete_damage",
                "elastic_modulus_mpa": 30_000.0,
                "tensile_strength_mpa": 3.0,
                "compressive_strength_mpa": 30.0,
                "tensile_softening_rate": 3_000.0,
                "compressive_softening_rate": 400.0,
                "history_tolerance": 1.0e-14,
            },
        ],
        "sections": [
            {
                "id": "RC1",
                "type": "rectangular_rc_fiber_section",
                "width_m": 0.4,
                "depth_m": 0.6,
                "cover_m": 0.05,
                "concrete_layer_count": 2,
                "top_bar_count": 4,
                "bottom_bar_count": 4,
                "bar_area_m2": 3.87e-4,
                "steel_material": "steel",
                "concrete_material": "concrete",
            }
        ],
        "loads": [
            {
                "node": "N2",
                "components": {
                    "FX": 0.0,
                    "FY": -10.0,
                    "FZ": 0.0,
                    "MX": 0.0,
                    "MY": 0.0,
                    "MZ": 0.0,
                },
            }
        ],
        "supports": [{"node": "N1", "dofs": ["UX", "UY", "RZ"]}],
        "unsupported_features": [],
        "warnings": [],
        "metadata": {"case_id": "public-rc-cantilever"},
    }


def _write_model(path: Path, payload: dict | None = None):
    path.write_text(
        json.dumps(payload or _payload(), sort_keys=True),
        encoding="utf-8",
    )
    return load_neutral_json(path)


@pytest.fixture(scope="module")
def solved(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("public-rc-fiber-frame")
    model_path = root / "model.json"
    model = _write_model(model_path)
    result = analyze_public_rc_fiber_frame(
        model,
        PublicRCFiberFrameConfig(load_steps=2),
    )
    return root, model_path, model, result


def test_public_api_returns_exact_authoritative_engineering_result(solved) -> None:
    _, _, _, result = solved
    report = validate_public_rc_fiber_frame_result(result)

    assert result.status == "ready"
    assert result.contract_pass is True
    assert report.contract_pass is True
    assert result.authority["reaction"] == "authoritative"
    assert result.authority["member_force"] == "authoritative"
    assert result.authority["section_resultant"] == "authoritative"
    assert result.authority["fiber_strain_stress"] == "authoritative"
    assert result.authority["engineering_design"] == "not_authoritative"
    assert result.metrics["exact_engineering_recovery"] is True
    assert result.metrics["state_bytes_exact"] is True
    assert result.metrics["fallback_count"] == 0
    assert result.metrics["regularization_count"] == 0
    assert len(result.node_displacements) == 2
    assert len(result.support_reactions) == 3
    assert len(result.member_end_forces) == 1
    assert len(result.section_results) == 2
    assert len(result.fiber_results) == 8
    assert result.node_displacements[1]["UY_m"] < 0.0
    reactions = {row["dof"]: row["value_si"] for row in result.support_reactions}
    assert reactions["UY"] == pytest.approx(10_000.0, abs=1.0e-6)
    assert abs(reactions["RZ"]) == pytest.approx(30_000.0, abs=1.0e-5)
    assert result.to_dict()["result_hash"] == result.result_hash
    assert "checkpoint_artifact" not in result.to_dict()


def test_exact_prefix_restart_replays_to_same_terminal_authority(solved) -> None:
    _, _, model, first = solved
    prefix = first.checkpoint_artifact(1)
    resumed = analyze_public_rc_fiber_frame(
        model,
        PublicRCFiberFrameConfig(load_steps=2),
        restart_checkpoint_chain=prefix,
    )

    assert resumed.status == "ready"
    assert resumed.contract_pass is True
    assert resumed.metrics["replayed_prefix_step_count"] == 1
    assert resumed.metrics["newly_solved_step_count"] == 1
    assert (
        resumed.contract_bindings["engineering_result_hash"]
        == (first.contract_bindings["engineering_result_hash"])
    )
    assert (
        resumed.contract_bindings["checkpoint_chain_hash"]
        == (first.contract_bindings["checkpoint_chain_hash"])
    )
    assert resumed.node_displacements == first.node_displacements
    assert resumed.support_reactions == first.support_reactions
    assert resumed.member_end_forces == first.member_end_forces
    assert resumed.section_results == first.section_results
    assert resumed.fiber_results == first.fiber_results
    assert resumed.checkpoint_artifact() == first.checkpoint_artifact()


def test_tampered_restart_fails_closed_before_solver_execution(solved) -> None:
    _, _, model, result = solved
    tampered = bytearray(result.checkpoint_artifact(1))
    tampered[-2] = ord("0") if tampered[-2] != ord("0") else ord("1")

    blocked = analyze_public_rc_fiber_frame(
        model,
        PublicRCFiberFrameConfig(load_steps=2),
        restart_checkpoint_chain=tampered,
    )

    assert blocked.status == "blocked"
    assert blocked.contract_pass is False
    assert blocked.metrics["solver_executed"] is False
    assert blocked.checkpoint["available"] is False
    assert blocked.unsupported_features[0]["kind"] == (
        "rc_fiber_frame_checkpoint_restart_invalid"
    )


def test_solver_contract_error_without_restart_is_not_mislabeled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _write_model(tmp_path / "solver-error.json")

    def fail_execution(*_args, **_kwargs):
        raise ValueError("synthetic execution contract failure")

    monkeypatch.setattr(nonlinear_fiber_frame, "_run_load_path", fail_execution)
    blocked = nonlinear_fiber_frame.analyze_public_rc_fiber_frame(
        model,
        PublicRCFiberFrameConfig(load_steps=2),
    )

    assert blocked.status == "blocked"
    assert blocked.unsupported_features[0]["kind"] == (
        "rc_fiber_frame_execution_failed"
    )
    assert blocked.unsupported_features[0]["path"] == "/solver"


def test_release_or_offset_semantics_fail_closed_before_solve(tmp_path: Path) -> None:
    payload = _payload()
    payload["elements"][0]["release_i"] = ["RZ"]
    model = _write_model(tmp_path / "released.json", payload)

    result = analyze_public_rc_fiber_frame(model)

    assert result.status == "blocked"
    assert result.metrics["solver_executed"] is False
    assert result.unsupported_features[0]["kind"] == ("rc_fiber_frame_row_keys_invalid")


def test_branched_topology_fails_closed_before_solve(tmp_path: Path) -> None:
    payload = _payload()
    payload["nodes"] = [
        {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
        {"id": "N2", "coordinates": [1.0, 0.0, 0.0]},
        {"id": "N3", "coordinates": [2.0, 1.0, 0.0]},
        {"id": "N4", "coordinates": [2.0, -1.0, 0.0]},
    ]
    payload["elements"] = [
        {
            "id": f"M{index}",
            "type": "stateful_rc_fiber_frame2d",
            "nodes": list(nodes),
            "section": "RC1",
            "integration_order": 2,
        }
        for index, nodes in enumerate(
            (("N1", "N2"), ("N2", "N3"), ("N2", "N4")),
            start=1,
        )
    ]
    payload["loads"][0]["node"] = "N3"
    model = _write_model(tmp_path / "branched.json", payload)

    result = analyze_public_rc_fiber_frame(model)

    assert result.status == "blocked"
    assert result.metrics["solver_executed"] is False
    assert result.unsupported_features[0]["kind"] == (
        "rc_fiber_frame_topology_not_serial_chain"
    )


def test_cli_writes_result_report_and_exact_checkpoint_atomically(
    solved,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, model_path, _, result = solved
    out = root / "cli-result.json"
    report_out = root / "cli-report.json"
    checkpoint_out = root / "cli-checkpoint.json"
    source_text = model_path.read_text(encoding="utf-8")

    monkeypatch.setattr(
        nonlinear_fiber_frame_cli,
        "analyze_public_rc_fiber_frame",
        lambda *_args, **_kwargs: result,
    )
    exit_code = nonlinear_fiber_frame_cli.main(
        [
            str(model_path),
            "--load-steps",
            "2",
            "--out",
            str(out),
            "--report-out",
            str(report_out),
            "--checkpoint-out",
            str(checkpoint_out),
        ]
    )

    assert exit_code == 0
    assert model_path.read_text(encoding="utf-8") == source_text
    assert json.loads(out.read_text(encoding="utf-8"))["contract_pass"] is True
    assert (
        json.loads(report_out.read_text(encoding="utf-8"))["exact_engineering_recovery"]
        is True
    )
    assert checkpoint_out.read_bytes() == result.checkpoint_artifact()


def test_cli_rejects_checkpoint_output_aliasing_restart_input(
    solved,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, model_path, _, result = solved
    restart = root / "restart.json"
    restart.write_bytes(result.checkpoint_artifact(1))
    analysis_started = False

    def unexpected_analysis(*_args, **_kwargs):
        nonlocal analysis_started
        analysis_started = True
        raise AssertionError("analysis must not start for colliding paths")

    monkeypatch.setattr(
        nonlinear_fiber_frame_cli,
        "analyze_public_rc_fiber_frame",
        unexpected_analysis,
    )
    with pytest.raises(SystemExit):
        nonlinear_fiber_frame_cli.main(
            [
                str(model_path),
                "--restart-from",
                str(restart),
                "--out",
                str(root / "alias-result.json"),
                "--report-out",
                str(root / "alias-report.json"),
                "--checkpoint-out",
                str(restart),
            ]
        )

    assert analysis_started is False


def test_blocked_cli_clears_stale_checkpoint_output(tmp_path: Path) -> None:
    payload = _payload()
    payload["elements"][0]["release_i"] = ["RZ"]
    model_path = tmp_path / "unsupported.json"
    _write_model(model_path, payload)
    result_path = tmp_path / "blocked-result.json"
    report_path = tmp_path / "blocked-report.json"
    checkpoint_path = tmp_path / "stale-checkpoint.json"
    checkpoint_path.write_bytes(b"stale checkpoint bytes")

    exit_code = nonlinear_fiber_frame_cli.main(
        [
            str(model_path),
            "--out",
            str(result_path),
            "--report-out",
            str(report_path),
            "--checkpoint-out",
            str(checkpoint_path),
        ]
    )

    assert exit_code == 2
    assert json.loads(result_path.read_text(encoding="utf-8"))["status"] == "blocked"
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "blocked"
    assert not checkpoint_path.exists()


def test_three_file_output_failure_rolls_back_every_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_path = tmp_path / "result.json"
    report_path = tmp_path / "report.json"
    checkpoint_path = tmp_path / "checkpoint.json"
    originals = (b"old result\n", b"old report\n", b"old checkpoint\n")
    for path, payload in zip(
        (result_path, report_path, checkpoint_path),
        originals,
        strict=True,
    ):
        path.write_bytes(payload)
    real_replace = _output_integrity.os.replace
    call_count = 0

    def fail_third_replace(source: str | Path, target: str | Path) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            raise OSError("third replacement failed")
        real_replace(source, target)

    monkeypatch.setattr(_output_integrity.os, "replace", fail_third_replace)
    with pytest.raises(OSError, match="third replacement failed"):
        _output_integrity.write_json_pair_and_bytes(
            result_path,
            {"status": "new result"},
            report_path,
            {"status": "new report"},
            checkpoint_path,
            b"new checkpoint\n",
        )

    assert result_path.read_bytes() == originals[0]
    assert report_path.read_bytes() == originals[1]
    assert checkpoint_path.read_bytes() == originals[2]


def test_stale_checkpoint_removal_failure_rolls_back_json_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_path = tmp_path / "result.json"
    report_path = tmp_path / "report.json"
    checkpoint_path = tmp_path / "checkpoint.json"
    result_path.write_bytes(b"old result\n")
    report_path.write_bytes(b"old report\n")
    checkpoint_path.write_bytes(b"old checkpoint\n")
    real_unlink = Path.unlink

    def fail_checkpoint_unlink(path: Path, *args, **kwargs) -> None:
        if path == checkpoint_path:
            raise OSError("checkpoint removal failed")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_checkpoint_unlink)
    with pytest.raises(OSError, match="checkpoint removal failed"):
        _output_integrity.write_json_pair_and_clear_artifact(
            result_path,
            {"status": "new result"},
            report_path,
            {"status": "new report"},
            checkpoint_path,
        )

    assert result_path.read_bytes() == b"old result\n"
    assert report_path.read_bytes() == b"old report\n"
    assert checkpoint_path.read_bytes() == b"old checkpoint\n"


def test_config_requires_j5_compatible_full_path() -> None:
    with pytest.raises(ValueError, match="load_steps"):
        PublicRCFiberFrameConfig(load_steps=1)
    with pytest.raises(ValueError, match="residual_tolerance"):
        PublicRCFiberFrameConfig(residual_tolerance=0.0)


def test_console_entrypoint_is_registered() -> None:
    pyproject_target = (
        "structural-analysis-nonlinear-fiber-frame = "
        '"structural_analysis.api.nonlinear_fiber_frame_cli:main"'
    )
    setup_target = (
        "structural-analysis-nonlinear-fiber-frame = "
        "structural_analysis.api.nonlinear_fiber_frame_cli:main"
    )
    assert pyproject_target in (REPO_ROOT / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert setup_target in (REPO_ROOT / "setup.cfg").read_text(encoding="utf-8")


def test_documented_example_matches_the_exact_compiler_profile() -> None:
    model = load_neutral_json(
        REPO_ROOT / "examples" / "public_rc_fiber_frame_cantilever.json"
    )
    result = analyze_public_rc_fiber_frame(
        model,
        PublicRCFiberFrameConfig(load_steps=2),
        restart_checkpoint_chain=b"not-json",
    )
    assert result.unsupported_features[0]["kind"] == (
        "rc_fiber_frame_checkpoint_restart_invalid"
    )


def test_model_snapshot_is_not_mutated_by_compile(solved) -> None:
    _, _, model, _ = solved
    before = deepcopy(model.canonical_payload())
    analyze_public_rc_fiber_frame(
        model,
        PublicRCFiberFrameConfig(load_steps=2),
        restart_checkpoint_chain=b"not-json",
    )
    assert model.canonical_payload() == before


def _canonical_restart_bytes(payload: dict) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _independent_chain_hash(payload: dict, checkpoints: tuple) -> str:
    # Independent chain framing/digest oracle; per-checkpoint bytes still use
    # the production codec, so this is not an independent checkpoint codec.
    raw = bytearray(b"structural-analysis/stateful-fiber-frame2d-checkpoint-chain/v1\0")
    for key in ("role", "storage_profile", "case_id", "problem_contract_hash"):
        value = payload[key].encode("utf-8")
        raw.extend(struct.pack("<Q", len(value)))
        raw.extend(value)
    raw.extend(struct.pack("<Q", len(checkpoints)))
    for checkpoint in checkpoints:
        value = checkpoint.canonical_bytes()
        raw.extend(struct.pack("<Q", len(value)))
        raw.extend(value)
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("kind", [bytes, bytearray, memoryview])
def test_neutral_bytes_to_restart_preserves_numeric_metadata_and_source_digest(kind):
    payload = _payload()
    payload["metadata"].update({"negative_zero": -0.0, "large_integer": 2**60 + 1})
    raw = json.dumps(payload, indent=2).encode("utf-8") + b"\n"
    model = load_neutral_json_bytes(kind(raw), source_path="memory://rc-input.json")
    expected_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    before = model.canonical_payload()
    assert model.input_checksum == expected_digest
    assert type(model.metadata["large_integer"]) is int
    assert model.metadata["large_integer"] == 2**60 + 1
    assert math.copysign(1.0, model.metadata["negative_zero"]) == -1.0

    config = PublicRCFiberFrameConfig(load_steps=2)
    first = analyze_public_rc_fiber_frame(model, config)
    assert first.status == "ready"
    prefix = first.checkpoint_artifact(1)
    compact = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    equivalent = load_neutral_json_bytes(kind(compact))
    compact_digest = "sha256:" + hashlib.sha256(compact).hexdigest()
    assert compact_digest != expected_digest
    assert equivalent.canonical_model_checksum == model.canonical_model_checksum
    resumed = analyze_public_rc_fiber_frame(
        equivalent, config, restart_checkpoint_chain=kind(prefix),
    )
    assert resumed.status == "ready"
    assert resumed.contract_pass is True
    assert first.input_checksum == expected_digest
    assert resumed.input_checksum == compact_digest
    assert resumed.canonical_model_checksum == model.canonical_model_checksum
    assert resumed.configuration["restart_checkpoint_artifact_hash"] == (
        "sha256:" + hashlib.sha256(prefix).hexdigest()
    )
    assert resumed.checkpoint_artifact() == first.checkpoint_artifact()
    assert resumed.contract_bindings["engineering_result_hash"] == (
        first.contract_bindings["engineering_result_hash"]
    )
    assert model.canonical_payload() == before
    assert math.copysign(1.0, model.metadata["negative_zero"]) == -1.0


def test_public_checkpoint_bytes_have_independent_chain_and_artifact_digests(solved):
    _, _, model, result = solved
    raw = result.checkpoint_artifact()
    payload = json.loads(raw)
    assert _canonical_restart_bytes(payload) == raw
    assert payload["storage_profile"] == "canonical-signed-zero-preserving-utf8-json.v1"
    assert payload["chain_hash"] == _independent_chain_hash(
        payload, result._checkpoint_chain.checkpoints,
    )
    resumed = analyze_public_rc_fiber_frame(
        model, PublicRCFiberFrameConfig(load_steps=2), restart_checkpoint_chain=raw,
    )
    assert resumed.status == "ready"
    assert resumed.metrics["replayed_prefix_step_count"] == 2
    assert resumed.metrics["newly_solved_step_count"] == 0
    assert resumed.configuration["restart_checkpoint_artifact_hash"] == (
        "sha256:" + hashlib.sha256(raw).hexdigest()
    )
    assert resumed.checkpoint_artifact() == raw


@pytest.mark.parametrize(
    "mutation",
    [
        "truncated-tail", "truncated-middle", "chain-checksum", "terminal-checksum",
        "state-checksum", "signed-zero", "large-integer", "uint64-overflow",
        "boolean-epoch", "float-epoch", "missing-root", "missing-ancestor",
    ],
)
def test_restart_adversarial_corpus_never_reaches_solver(solved, monkeypatch, mutation):
    _, _, model, result = solved
    original = result.checkpoint_artifact()
    payload = json.loads(original)
    if mutation == "truncated-tail":
        raw = original[:-1]
    elif mutation == "truncated-middle":
        raw = original[:len(original) // 2]
    else:
        if mutation in ("chain-checksum", "terminal-checksum"):
            key = (
                "chain_hash" if mutation == "chain-checksum" else "terminal_state_hash"
            )
            payload[key] = "sha256:" + "0" * 64
        elif mutation == "state-checksum":
            payload["checkpoints"][-1]["state_hash"] = "sha256:" + "0" * 64
        elif mutation == "signed-zero":
            # Numerically equal, but the immutable state bytes have changed.
            zero = payload["checkpoints"][0]["global_displacements"][0]
            assert zero == 0.0
            payload["checkpoints"][0]["global_displacements"][0] = -float(zero)
        elif mutation in (
            "large-integer", "uint64-overflow", "boolean-epoch", "float-epoch",
        ):
            payload["checkpoints"][-1]["epoch"] = {
                "large-integer": 2**60 + 1,
                "uint64-overflow": 2**64,
                "boolean-epoch": True,
                "float-epoch": 2.0,
            }[mutation]
        else:
            removed = 0 if mutation == "missing-root" else 1
            checkpoints = tuple(
                row for index, row in enumerate(result._checkpoint_chain.checkpoints)
                if index != removed
            )
            del payload["checkpoints"][removed]
            payload["checkpoint_count"] = len(checkpoints)
            payload["root_state_hash"] = checkpoints[0].state_hash
            # Repair the container hash so rejection actually requires ancestry.
            payload["chain_hash"] = _independent_chain_hash(payload, checkpoints)
        raw = _canonical_restart_bytes(payload)
    assert raw != original
    before = model.canonical_payload()

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid restart reached the nonlinear load-path solver")

    monkeypatch.setattr(
        nonlinear_fiber_frame, "run_stateful_fiber_frame2d_load_path", forbidden,
    )
    blocked = analyze_public_rc_fiber_frame(
        model, PublicRCFiberFrameConfig(load_steps=2), restart_checkpoint_chain=raw,
    )
    assert blocked.status == "blocked"
    assert blocked.contract_pass is False
    assert blocked.metrics["solver_executed"] is False
    assert blocked.checkpoint["available"] is False
    assert blocked.unsupported_features[0]["kind"] == (
        "rc_fiber_frame_checkpoint_restart_invalid"
    )
    assert blocked.configuration["restart_checkpoint_artifact_hash"] == (
        "sha256:" + hashlib.sha256(raw).hexdigest()
    )
    assert model.canonical_payload() == before
    assert result.checkpoint_artifact() == original
    with pytest.raises(ValueError, match="no checkpoint artifact"):
        blocked.checkpoint_artifact()
