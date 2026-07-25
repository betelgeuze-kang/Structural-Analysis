from pathlib import Path

source_path = Path("benchmarks/clean-runners/opensees-calculix/run_clean_runner.py")
source = source_path.read_text(encoding="utf-8")

schema_marker = '''SCHEMA_RELATIVE_PATH = Path(
    "src/structural_analysis/schemas/external_vv_clean_runner_receipt_v1.schema.json"
)
'''
schema_replacement = schema_marker + '''CODE_RECEIPT_SCHEMA_RELATIVE_PATH = Path(
    "src/structural_analysis/schemas/"
    "external_code_to_code_technical_receipt_v1.schema.json"
)
MODAL_RECEIPT_SCHEMA_RELATIVE_PATH = Path(
    "src/structural_analysis/schemas/"
    "external_modal_buckling_technical_receipt_v1.schema.json"
)
COMMITTED_BUNDLE_RELATIVE_DIR = Path(
    "artifacts/vv/opensees_calculix_clean_runner"
)
CHILD_RECEIPT_POLICY = {
    "code_to_code": (
        "external_code_to_code_receipt.json",
        CODE_RECEIPT_SCHEMA_RELATIVE_PATH,
    ),
    "modal_buckling": (
        "external_modal_buckling_receipt.json",
        MODAL_RECEIPT_SCHEMA_RELATIVE_PATH,
    ),
}
'''
if source.count(schema_marker) != 1:
    raise SystemExit("schema constants marker did not match exactly once")
source = source.replace(schema_marker, schema_replacement)

asset_function = '''def _validate_assets(asset_dir: Path) -> list[Path]:
    actual_names = {path.name for path in asset_dir.iterdir() if path.is_file()}
    missing = sorted(set(ASSET_POLICY) - actual_names)
    if missing:
        raise CleanRunnerError("external_assets_missing:" + ",".join(missing))
    assets = [asset_dir / name for name in sorted(ASSET_POLICY)]
    mismatches = [
        path.name
        for path in assets
        if _file_hash(path) != "sha256:" + ASSET_POLICY[path.name]
    ]
    if mismatches:
        raise CleanRunnerError(
            "external_asset_checksum_mismatch:" + ",".join(mismatches)
        )
    return assets
'''
asset_replacement = '''def _validate_assets(asset_dir: Path, repo_root: Path) -> list[Path]:
    asset_root = asset_dir.resolve()
    repository_root = repo_root.resolve()
    actual_names = {path.name for path in asset_dir.iterdir() if path.is_file()}
    missing = sorted(set(ASSET_POLICY) - actual_names)
    if missing:
        raise CleanRunnerError("external_assets_missing:" + ",".join(missing))
    assets: list[Path] = []
    for name in sorted(ASSET_POLICY):
        path = asset_dir / name
        if path.is_symlink():
            raise CleanRunnerError("external_asset_symlink_forbidden:" + name)
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(asset_root)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            raise CleanRunnerError("external_asset_path_invalid:" + name) from exc
        try:
            resolved.relative_to(repository_root)
        except ValueError:
            pass
        else:
            raise CleanRunnerError("external_asset_inside_repository:" + name)
        if not resolved.is_file():
            raise CleanRunnerError("external_asset_regular_file_required:" + name)
        if _file_hash(resolved) != "sha256:" + ASSET_POLICY[name]:
            raise CleanRunnerError("external_asset_checksum_mismatch:" + name)
        assets.append(resolved)
    return assets
'''
if source.count(asset_function) != 1:
    raise SystemExit("asset validation function did not match exactly once")
source = source.replace(asset_function, asset_replacement)

product_validator_marker = '''def _validate_product_receipt(
    receipt: dict[str, Any], *, expected_fresh_execution: bool = True
) -> None:
    if receipt.get("technical_contract_pass") is not True:
'''
product_validator_replacement = '''def _validated_child_receipt_path(
    *,
    repo_root: Path,
    name: str,
    descriptor: dict[str, Any],
) -> Path:
    if name not in CHILD_RECEIPT_POLICY:
        raise CleanRunnerError("summary_child_receipt_name_invalid")
    expected_filename, _schema_path = CHILD_RECEIPT_POLICY[name]
    expected_relative = COMMITTED_BUNDLE_RELATIVE_DIR / expected_filename
    raw_path = descriptor.get("path")
    if not isinstance(raw_path, str):
        raise CleanRunnerError("summary_child_receipt_path_invalid")
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts or relative != expected_relative:
        raise CleanRunnerError("summary_child_receipt_path_invalid")
    candidate = (repo_root / relative).resolve()
    expected = (repo_root / expected_relative).resolve()
    if candidate != expected:
        raise CleanRunnerError("summary_child_receipt_path_invalid")
    return candidate


def _validate_product_receipt(
    receipt: dict[str, Any],
    *,
    expected_fresh_execution: bool = True,
    schema_path: Path | None = None,
) -> None:
    if schema_path is not None:
        schema = _read_json(schema_path)
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(receipt),
            key=lambda row: list(row.absolute_path),
        )
        if errors:
            raise CleanRunnerError("product_receipt_schema_invalid")
    if receipt.get("artifact_hash") != _artifact_hash(receipt):
        raise CleanRunnerError("product_receipt_artifact_hash_invalid")
    if receipt.get("technical_contract_pass") is not True:
'''
if source.count(product_validator_marker) != 1:
    raise SystemExit("product validator marker did not match exactly once")
source = source.replace(product_validator_marker, product_validator_replacement)

level2_block = '''    if receipt.get("claims", {}).get("verification_level_2") is not False:
        raise CleanRunnerError("product_receipt_level2_promotion_forbidden")
    replay = receipt.get("replay_provenance", {})
'''
level2_replacement = '''    claims = receipt.get("claims", {})
    if claims.get("verification_level_2") is not False:
        raise CleanRunnerError("product_receipt_level2_promotion_forbidden")
    for forbidden in ("commercial_equivalence", "design_authority", "release_readiness"):
        if claims.get(forbidden) is not False:
            raise CleanRunnerError("product_receipt_claim_promotion_forbidden")
    replay = receipt.get("replay_provenance", {})
'''
if source.count(level2_block) != 1:
    raise SystemExit("claim validation marker did not match exactly once")
source = source.replace(level2_block, level2_replacement)

child_block = '''    child_receipts = {
        name: _read_json(repo_root / descriptor["path"])
        for name, descriptor in payload["product_receipts"].items()
    }
    for name, receipt in child_receipts.items():
        descriptor = payload["product_receipts"][name]
        path = repo_root / descriptor["path"]
        if (
            descriptor["file_sha256"] != _file_hash(path)
            or descriptor["artifact_hash"] != receipt["artifact_hash"]
            or descriptor["source_set_hash"]
            != receipt["internal_source"]["source_set_hash"]
        ):
            raise CleanRunnerError("summary_child_receipt_descriptor_invalid")
        _validate_product_receipt(receipt, expected_fresh_execution=False)
        if descriptor["fresh_external_runtime_execution"] is not (
            _receipt_fresh_execution(receipt)
        ):
            raise CleanRunnerError("summary_child_replay_descriptor_invalid")
'''
child_replacement = '''    child_receipts: dict[str, dict[str, Any]] = {}
    for name, descriptor in payload["product_receipts"].items():
        path = _validated_child_receipt_path(
            repo_root=repo_root,
            name=name,
            descriptor=descriptor,
        )
        receipt = _read_json(path)
        _expected_filename, schema_relative_path = CHILD_RECEIPT_POLICY[name]
        _validate_product_receipt(
            receipt,
            expected_fresh_execution=False,
            schema_path=repo_root / schema_relative_path,
        )
        child_receipts[name] = receipt
        if (
            descriptor["file_sha256"] != _file_hash(path)
            or descriptor["artifact_hash"] != receipt["artifact_hash"]
            or descriptor["source_set_hash"]
            != receipt["internal_source"]["source_set_hash"]
        ):
            raise CleanRunnerError("summary_child_receipt_descriptor_invalid")
        if descriptor["fresh_external_runtime_execution"] is not (
            _receipt_fresh_execution(receipt)
        ):
            raise CleanRunnerError("summary_child_replay_descriptor_invalid")
'''
if source.count(child_block) != 1:
    raise SystemExit("summary child validation block did not match exactly once")
source = source.replace(child_block, child_replacement)

refresh_calls = '''    _validate_product_receipt(code_receipt, expected_fresh_execution=False)
    _validate_product_receipt(modal_receipt, expected_fresh_execution=False)
'''
refresh_replacement = '''    _validate_product_receipt(
        code_receipt,
        expected_fresh_execution=False,
        schema_path=repo_root / CODE_RECEIPT_SCHEMA_RELATIVE_PATH,
    )
    _validate_product_receipt(
        modal_receipt,
        expected_fresh_execution=False,
        schema_path=repo_root / MODAL_RECEIPT_SCHEMA_RELATIVE_PATH,
    )
'''
if source.count(refresh_calls) != 1:
    raise SystemExit("refresh child validation calls did not match exactly once")
source = source.replace(refresh_calls, refresh_replacement)

main_calls = '''    _validate_product_receipt(code_receipt)
    _validate_product_receipt(modal_receipt)
'''
main_replacement = '''    _validate_product_receipt(
        code_receipt,
        schema_path=repo_root / CODE_RECEIPT_SCHEMA_RELATIVE_PATH,
    )
    _validate_product_receipt(
        modal_receipt,
        schema_path=repo_root / MODAL_RECEIPT_SCHEMA_RELATIVE_PATH,
    )
'''
if source.count(main_calls) != 1:
    raise SystemExit("main child validation calls did not match exactly once")
source = source.replace(main_calls, main_replacement)

asset_call = '''    assets = _validate_assets(asset_dir)
'''
asset_call_replacement = '''    assets = _validate_assets(asset_dir, repo_root)
'''
if source.count(asset_call) != 1:
    raise SystemExit("main asset validation call did not match exactly once")
source_path.write_text(source.replace(asset_call, asset_call_replacement), encoding="utf-8")

test_path = Path("tests/test_external_vv_clean_runner_contract.py")
tests = test_path.read_text(encoding="utf-8")
insertion_marker = '''def test_rehashed_level2_or_independent_operator_promotion_is_rejected() -> None:
'''
new_tests = '''def test_symlinked_external_assets_are_rejected(tmp_path: Path) -> None:
    target = ROOT / "README.md"
    try:
        for name in runner.ASSET_POLICY:
            (tmp_path / name).symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable in this environment")

    with pytest.raises(
        runner.CleanRunnerError,
        match="external_asset_symlink_forbidden",
    ):
        runner._validate_assets(tmp_path, ROOT)


def test_rehashed_summary_cannot_traverse_outside_the_clean_runner_bundle() -> None:
    payload = deepcopy(_json(SUMMARY))
    payload["product_receipts"]["code_to_code"]["path"] = (
        "artifacts/vv/opensees_calculix_clean_runner/../../../"
        "implementation/phase1/release_evidence/productization/"
        "external_code_to_code_technical_execution_receipt.json"
    )
    payload["artifact_hash"] = runner._artifact_hash(payload)

    with pytest.raises(
        runner.CleanRunnerError,
        match="summary_child_receipt_path_invalid",
    ):
        runner.validate_summary(payload, repo_root=ROOT)


def test_modified_child_receipt_requires_a_valid_schema_bound_artifact_hash() -> None:
    receipt = deepcopy(_json(CODE_RECEIPT))
    receipt["generated_at"] = "2000-01-01T00:00:00+00:00"

    with pytest.raises(
        runner.CleanRunnerError,
        match="product_receipt_artifact_hash_invalid",
    ):
        runner._validate_product_receipt(
            receipt,
            expected_fresh_execution=False,
            schema_path=ROOT / runner.CODE_RECEIPT_SCHEMA_RELATIVE_PATH,
        )


def test_rehashed_level2_or_independent_operator_promotion_is_rejected() -> None:
'''
if tests.count(insertion_marker) != 1:
    raise SystemExit("clean-runner test insertion marker did not match exactly once")
test_path.write_text(tests.replace(insertion_marker, new_tests), encoding="utf-8")
