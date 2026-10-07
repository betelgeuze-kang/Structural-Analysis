"""Keep strict modal receipt consumers behind current-source generation/replay."""

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PREP = "      - name: Materialize exact current-source test evidence\n"
GENERATE = "python scripts/build_phase2_whole_model_modal_artifacts.py"
CHECK = GENERATE + " --check"
CONSUMER = "python scripts/run_external_code_to_code_technical_receipt.py"
WORKFLOWS = (
    ("ci.yml", 1),
    ("python-test-collection.yml", 1),
    ("nightly-full-quality.yml", 2),
    ("nightly-heavy-solver.yml", 1),
)


def _assert_modal_preparation(workflow: str, expected_blocks: int) -> None:
    blocks = workflow.split(PREP)[1:]
    assert len(blocks) == expected_blocks
    for block in blocks:
        preparation = block.split("\n      - name:", 1)[0]
        _assert_pair_before_consumer(preparation, GENERATE)
        # Default outputs are consumed later; do not bypass or weaken --check.
        assert "--result-out" not in preparation
        assert "--summary-out" not in preparation


def _assert_pair_before_consumer(preparation: str, generate: str) -> None:
    check = generate + " --check"
    lines = [line.strip() for line in preparation.splitlines()]
    assert lines.count(generate) == 1
    assert lines.count(check) == 1
    assert lines.index(generate) < lines.index(check)
    assert preparation.index(check) < preparation.index(CONSUMER)


@pytest.mark.parametrize("filename,expected_blocks", WORKFLOWS)
def test_each_modal_consumer_prepares_current_source_receipts(
    filename: str,
    expected_blocks: int,
) -> None:
    workflow = (ROOT / ".github" / "workflows" / filename).read_text()
    _assert_modal_preparation(workflow, expected_blocks)


@pytest.mark.parametrize(
    "generate",
    [
        GENERATE,
        "python scripts/build_analytic_frame_verification_artifact.py",
        "python scripts/build_phase2_whole_model_buckling_artifacts.py",
    ],
)
@pytest.mark.parametrize(
    "mutation", ["missing_generate", "missing_check", "reversed", "late"]
)
def test_modal_preparation_contract_rejects_missing_or_late_generation(
    mutation: str,
    generate: str,
) -> None:
    generation = "          " + generate + "\n"
    check = "          " + generate + " --check\n"
    consumer = "          " + CONSUMER + "\n"
    valid = PREP + "        run: |\n" + generation + check + consumer
    _assert_pair_before_consumer(valid, generate)
    if mutation == "missing_generate":
        invalid = valid.replace(generation, "")
    elif mutation == "missing_check":
        invalid = valid.replace(check, "")
    elif mutation == "reversed":
        invalid = valid.replace(generation + check, check + generation)
    else:
        invalid = valid.replace(
            generation + check + consumer, consumer + generation + check
        )
    with pytest.raises(AssertionError):
        _assert_pair_before_consumer(invalid, generate)


def test_heavy_prepares_all_changed_mechanics_sources_before_consumers() -> None:
    workflow = (ROOT / ".github/workflows/nightly-heavy-solver.yml").read_text()
    preparation = workflow.split(PREP)[1].split("\n      - name:", 1)[0]
    generators = [
        "python scripts/build_analytic_frame_verification_artifact.py",
        "python scripts/build_phase2_whole_model_buckling_artifacts.py",
        GENERATE,
    ]
    for generate in generators:
        _assert_pair_before_consumer(preparation, generate)
    positions = [preparation.index(generate) for generate in generators]
    assert positions == sorted(positions)
