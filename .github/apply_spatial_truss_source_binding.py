from pathlib import Path

script_path = Path("scripts/run_external_code_to_code_technical_receipt.py")
source = script_path.read_text(encoding="utf-8")
old = '''    Path("src/structural_analysis/api/nonlinear_frame.py"),
    Path("src/structural_analysis/benchmark/analytic_frame.py"),
    Path("src/structural_analysis/assembly/stateful_corotational_fiber_frame2d.py"),
'''
new = '''    Path("src/structural_analysis/api/nonlinear_frame.py"),
    Path("src/structural_analysis/assembly/linear_static.py"),
    Path("src/structural_analysis/benchmark/analytic_frame.py"),
    Path("src/structural_analysis/assembly/stateful_corotational_fiber_frame2d.py"),
    Path("src/structural_analysis/elements/axial.py"),
'''
if source.count(old) != 1:
    raise SystemExit(f"source replacement count was {source.count(old)} instead of 1")
script_path.write_text(source.replace(old, new), encoding="utf-8")

test_path = Path("tests/test_external_code_to_code_technical_receipt.py")
tests = test_path.read_text(encoding="utf-8")
marker = '''    module.validate_external_code_to_code_technical_receipt(
        payload,
        repo_root=ROOT,
        require_current_sources=True,
    )

    assert payload["status"] == "partial"
'''
replacement = '''    module.validate_external_code_to_code_technical_receipt(
        payload,
        repo_root=ROOT,
        require_current_sources=True,
    )

    source_checksums = payload["internal_source"]["input_checksums"]
    assert "src/structural_analysis/assembly/linear_static.py" in source_checksums
    assert "src/structural_analysis/elements/axial.py" in source_checksums
    assert payload["status"] == "partial"
'''
if tests.count(marker) != 1:
    raise SystemExit(f"test replacement count was {tests.count(marker)} instead of 1")
test_path.write_text(tests.replace(marker, replacement), encoding="utf-8")
