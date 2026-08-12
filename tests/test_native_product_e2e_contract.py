from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_product_e2e.py"
SPEC = importlib.util.spec_from_file_location("check_native_product_e2e", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
product = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = product
SPEC.loader.exec_module(product)


def _copy_contract(tmp_path: Path) -> None:
    for relative in (
        "native/capabilities.json",
        *product.REQUIRED_TOKENS,
        *product.MODELIR_REQUIRED_TOKENS,
    ):
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def test_repository_product_e2e_contract_is_evidence_backed() -> None:
    report = product.check_product_e2e_contract(ROOT)

    assert report["contract_pass"] is True
    assert report["cutover_gate"] == "C5"
    assert report["blockers"] == []


def test_contract_fails_closed_when_clean_environment_evidence_disappears(
    tmp_path: Path,
) -> None:
    _copy_contract(tmp_path)
    path = (
        tmp_path / "native/crates/structural-cli/tests/nonlinear_ndtha_product_cli.rs"
    )
    text = path.read_text(encoding="utf-8").replace(
        "command.env_clear()", 'command.env_remove("PATH")'
    )
    path.write_text(text, encoding="utf-8")

    report = product.check_product_e2e_contract(tmp_path)

    assert report["contract_pass"] is False
    assert (
        "product_e2e_evidence_token_missing:"
        "native/crates/structural-cli/tests/nonlinear_ndtha_product_cli.rs:"
        "command.env_clear()" in report["blockers"]
    )
