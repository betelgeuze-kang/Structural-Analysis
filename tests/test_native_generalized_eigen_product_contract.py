from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_generalized_eigen_product.py"
SPEC = importlib.util.spec_from_file_location(
    "check_native_generalized_eigen_product", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
product = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = product
SPEC.loader.exec_module(product)


def _copy_contract(tmp_path: Path) -> None:
    for relative in {"native/capabilities.json", *product.REQUIRED_TOKENS}:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)


def test_repository_generalized_eigen_c4_c5_contract_is_evidence_backed() -> None:
    report = product.check_generalized_eigen_product(ROOT)

    assert report["contract_pass"] is True, report["blockers"]
    assert report["checkpoint_gate"] == "C4"
    assert report["product_gate"] == "C5"
    assert report["modelir_modal_product_gate"] == "C5"
    assert report["sequential_numerical_gate"] == "C1"
    assert "cannot promote C2 or C6" in report["claim_boundary"]


def test_contract_fails_closed_when_clean_environment_evidence_disappears(
    tmp_path: Path,
) -> None:
    _copy_contract(tmp_path)
    path = tmp_path / "native/crates/structural-cli/tests/dense_spectral_product_cli.rs"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "command.env_clear()", 'command.env_remove("PATH")'
        ),
        encoding="utf-8",
    )

    report = product.check_generalized_eigen_product(tmp_path)

    assert report["contract_pass"] is False
    assert any("command.env_clear()" in blocker for blocker in report["blockers"])
