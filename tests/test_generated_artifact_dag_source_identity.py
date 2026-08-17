from __future__ import annotations

import json
from pathlib import Path

import scripts.check_generated_artifact_dag as dag


def _write_product_state(root: Path, source: object) -> None:
    output = root / dag.EXPECTED_NODE_PATHS["product-state"]["outputs"][0]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"observed_github_main_source": source}),
        encoding="utf-8",
    )


def test_observed_product_state_source_reads_persisted_identity(tmp_path: Path) -> None:
    _write_product_state(tmp_path, "github_api_refs_heads_main_pre_build")

    assert (
        dag._observed_product_state_source(tmp_path)
        == "github_api_refs_heads_main_pre_build"
    )


def test_observed_product_state_source_rejects_missing_or_blank_identity(
    tmp_path: Path,
) -> None:
    assert dag._observed_product_state_source(tmp_path) is None
    _write_product_state(tmp_path, "   ")
    assert dag._observed_product_state_source(tmp_path) is None


def test_repo_root_parser_supports_separate_and_equals_forms(tmp_path: Path) -> None:
    assert dag._repo_root_from_argv(["--repo-root", str(tmp_path)]) == tmp_path
    assert dag._repo_root_from_argv([f"--repo-root={tmp_path}"]) == tmp_path


def test_cli_temporarily_uses_and_restores_persisted_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    persisted_source = "github_api_refs_heads_main_pre_build"
    _write_product_state(tmp_path, persisted_source)
    observed: list[str] = []
    original_source = dag._core.PRODUCT_STATE_NIGHTLY_SOURCE

    def fake_main(argv: list[str] | None = None) -> int:
        observed.append(dag._core.PRODUCT_STATE_NIGHTLY_SOURCE)
        return 0

    monkeypatch.setattr(dag._core, "main", fake_main)

    assert dag.main(["--repo-root", str(tmp_path)]) == 0
    assert observed == [persisted_source]
    assert dag._core.PRODUCT_STATE_NIGHTLY_SOURCE == original_source


def test_cli_without_persisted_product_state_keeps_original_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    observed: list[str] = []
    original_source = dag._core.PRODUCT_STATE_NIGHTLY_SOURCE

    def fake_main(argv: list[str] | None = None) -> int:
        observed.append(dag._core.PRODUCT_STATE_NIGHTLY_SOURCE)
        return 0

    monkeypatch.setattr(dag._core, "main", fake_main)

    assert dag.main(["--repo-root", str(tmp_path)]) == 0
    assert observed == [original_source]
    assert dag._core.PRODUCT_STATE_NIGHTLY_SOURCE == original_source
