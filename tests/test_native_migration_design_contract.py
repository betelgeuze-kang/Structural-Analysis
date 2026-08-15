from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1]
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
ADR = ROOT / "docs" / "adr" / "009-native-workspace-and-c-abi-v1.md"
NATIVE_DOCS = ROOT / "docs" / "native"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_native_adr_is_indexed_and_preserves_claim_boundary() -> None:
    index = _read(ADR_INDEX)
    adr = _read(ADR)

    assert "009-native-workspace-and-c-abi-v1.md" in index
    assert "ADR-009: Native Workspace and C ABI v1" in adr
    assert "supersede" in adr
    assert "G1 hardware freshness" in adr
    assert "Python" in adr and "oracle" in adr


@pytest.mark.parametrize(
    "name",
    (
        "README.md",
        "workspace-and-abi-v1.md",
        "python-native-parity-ledger.md",
        "modelir-v2-first-slice.md",
        "ci-contract.md",
        "existing-native-transition-plan.md",
    ),
)
def test_native_design_document_is_indexed(name: str) -> None:
    assert (NATIVE_DOCS / name).is_file()
    if name != "README.md":
        assert f"({name})" in _read(NATIVE_DOCS / "README.md")


def test_workspace_contract_has_complete_abi_status_taxonomy() -> None:
    contract = _read(NATIVE_DOCS / "workspace-and-abi-v1.md")
    rows = re.findall(
        r"^\| (\d+) \| (SA_[A-Z0-9_]+) \|",
        contract,
        flags=re.MULTILINE,
    )

    assert rows
    codes = [int(code) for code, _name in rows]
    names = [name for _code, name in rows]
    assert len(codes) == len(set(codes))
    assert len(names) == len(set(names))
    assert codes[0] == 0
    assert "SA_ERR_ABI_VERSION_MISMATCH" in names
    assert "SA_ERR_BUFFER_TOO_SMALL" in names
    assert "SA_ERR_FALLBACK_FORBIDDEN" in names
    assert "sa_get_api_v1" in contract
    assert "caller-owned" in contract
    assert "global mutable last-error" in contract


def test_parity_ledger_requires_every_cutover_stage_and_domain() -> None:
    ledger = _read(NATIVE_DOCS / "python-native-parity-ledger.md")

    for gate in range(7):
        assert f"C{gate}" in ledger
    for domain in range(1, 11):
        assert f"### D{domain}." in ledger

    ordered = (
        "C0 native unit",
        "C1 CPU oracle parity",
        "C2 CPU/HIP parity",
        "C3 Rust FFI integration",
        "C4 checkpoint/restart",
        "C5 bounded product E2E",
        "C6 decommission",
    )
    positions = [ledger.index(label) for label in ordered]
    assert positions == sorted(positions)
    assert "Python remains authoritative oracle" in ledger
    assert "g1_closure remains false" in ledger
    assert "self-hashed constrained-reaction ResultIR" in ledger
    assert "15-file terminal directories are byte-identical" in ledger
    assert "installed distribution v84" in ledger
    assert "rootfs diagnostic v7" in ledger


def test_modelir_slice_uses_tracked_non_lfs_fixtures() -> None:
    design = _read(NATIVE_DOCS / "modelir-v2-first-slice.md")
    fixture_paths = re.findall(
        r"^- ((?:tests/fixtures/model_ir_v2|examples)/[^\s]+\.json)$",
        design,
        flags=re.MULTILINE,
    )

    assert len(fixture_paths) >= 8
    for relative in fixture_paths:
        fixture = ROOT / relative
        assert fixture.is_file()
        first_line = fixture.read_text(encoding="utf-8").splitlines()[0]
        assert first_line != "version https://git-lfs.github.com/spec/v1"

    for failure in (
        "duplicate JSON key",
        "unknown non-extension field",
        "NaN, Infinity, -Infinity",
        "dangling node/material/section/reference",
        "load combination cycle",
        "undersized output buffer",
    ):
        assert failure in design


def test_ci_contract_keeps_hosted_and_hardware_lanes_separate() -> None:
    contract = _read(NATIVE_DOCS / "ci-contract.md")

    assert "pr-fast" in contract
    assert "merge-product" in contract
    assert "15 minutes" in contract
    assert "GitHub-hosted Linux CPU" in contract
    assert "hip-dedicated" in contract
    assert "generic service install/start/mutation" in contract
    assert "CPU fallback count 0" in contract
    assert "external runner boundary" in contract


def test_transition_plan_names_both_existing_rust_crates() -> None:
    plan = _read(NATIVE_DOCS / "existing-native-transition-plan.md")

    assert "structural_runtime_ffi/src/lib.rs" in plan
    assert "mgt_hip_full_residual_ffi/src/lib.rs" in plan
    assert "link-first" in plan
    assert "sa_get_api_v1" in plan
    assert "legacy source를 제거하지 않는다" in plan
