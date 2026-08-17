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


def test_product_state_validator_uses_and_restores_persisted_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    persisted_source = "github_api_refs_heads_main_pre_build"
    _write_product_state(tmp_path, persisted_source)
    observed: list[str] = []
    original_source = dag._core.PRODUCT_STATE_NIGHTLY_SOURCE

    def fake_validator(
        repo_root: Path,
        *,
        nightly_workflow_run_event: Path | None,
    ) -> list[str]:
        assert repo_root == tmp_path
        assert nightly_workflow_run_event == Path("nightly.json")
        observed.append(dag._core.PRODUCT_STATE_NIGHTLY_SOURCE)
        return []

    monkeypatch.setattr(dag, "_ORIGINAL_PRODUCT_STATE_VALIDATOR", fake_validator)

    assert (
        dag._validate_product_state_binding(
            tmp_path,
            nightly_workflow_run_event=Path("nightly.json"),
        )
        == []
    )
    assert observed == [persisted_source]
    assert dag._core.PRODUCT_STATE_NIGHTLY_SOURCE == original_source
