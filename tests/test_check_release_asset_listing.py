from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_release_asset_listing.py"
SPEC = importlib.util.spec_from_file_location("check_release_asset_listing", SCRIPT_PATH)
assert SPEC is not None
check_release_asset_listing = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_release_asset_listing)


def _manifest(tmp_path: Path) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "release_tag": "test-release",
                "artifacts": [
                    {
                        "asset_name": "required.zip",
                        "bytes": 10,
                        "sha256": "0" * 64,
                        "required": True,
                    },
                    {
                        "asset_name": "optional.pdf",
                        "bytes": 5,
                        "sha256": "1" * 64,
                        "required": False,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _assets(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "assets.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_compare_reports_missing_optional_and_extra_from_github_array(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    assets_path = _assets(
        tmp_path,
        [
            {"name": "required.zip", "size": 10},
            {"name": "extra.txt", "size": 1},
        ],
    )

    summary = check_release_asset_listing.check_release_asset_listing(manifest_path, assets_path)

    assert summary["ok"] is True
    assert summary["release_tag"] == "test-release"
    assert summary["matched"] == [{"name": "required.zip", "bytes": 10, "required": True}]
    assert summary["missing_optional"] == [{"name": "optional.pdf", "expected_bytes": 5}]
    assert summary["extra_assets"] == [{"name": "extra.txt", "bytes": 1}]
    assert summary["totals"]["manifest_assets"] == 2
    assert summary["totals"]["listed_assets"] == 2


def test_common_wrapped_assets_output_is_supported(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    assets_path = _assets(
        tmp_path,
        {
            "assets": [
                {"name": "required.zip", "size": 10},
                {"name": "optional.pdf", "size": 5},
            ]
        },
    )

    summary = check_release_asset_listing.check_release_asset_listing(manifest_path, assets_path, require_all=True)

    assert summary["ok"] is True
    assert summary["missing_required"] == []
    assert summary["missing_optional"] == []
    assert summary["size_mismatches"] == []


def test_gh_json_assets_output_is_supported(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    assets_path = _assets(
        tmp_path,
        [
            {
                "tagName": "test-release",
                "assets": [
                    {"name": "required.zip", "size": 10},
                    {"name": "optional.pdf", "size": 5},
                ],
            }
        ],
    )

    summary = check_release_asset_listing.check_release_asset_listing(manifest_path, assets_path)

    assert summary["ok"] is True
    assert len(summary["matched"]) == 2


def test_size_mismatch_fails_even_without_require_all(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    assets_path = _assets(tmp_path, [{"name": "required.zip", "size": 11}])

    summary = check_release_asset_listing.check_release_asset_listing(manifest_path, assets_path)

    assert summary["ok"] is False
    assert summary["exit_code"] == 1
    assert summary["size_mismatches"] == [
        {
            "name": "required.zip",
            "expected_bytes": 10,
            "actual_bytes": 11,
            "required": True,
        }
    ]


def test_require_all_fails_missing_required_asset(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    assets_path = _assets(tmp_path, [{"name": "optional.pdf", "size": 5}])

    summary = check_release_asset_listing.check_release_asset_listing(
        manifest_path,
        assets_path,
        require_all=True,
    )

    assert summary["ok"] is False
    assert summary["exit_code"] == 1
    assert summary["missing_required"] == [{"name": "required.zip", "expected_bytes": 10}]


def test_require_exact_fails_missing_optional_and_extra_assets(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    assets_path = _assets(
        tmp_path,
        [
            {"name": "required.zip", "size": 10},
            {"name": "extra.txt", "size": 1},
        ],
    )

    summary = check_release_asset_listing.check_release_asset_listing(
        manifest_path,
        assets_path,
        require_exact=True,
    )

    assert summary["ok"] is False
    assert summary["exit_code"] == 1
    assert summary["require_exact"] is True
    assert summary["missing_required"] == []
    assert summary["missing_optional"] == [{"name": "optional.pdf", "expected_bytes": 5}]
    assert summary["extra_assets"] == [{"name": "extra.txt", "bytes": 1}]
    assert summary["totals"]["missing_optional"] == 1
    assert summary["totals"]["extra_assets"] == 1


def test_require_exact_fails_missing_required_even_without_require_all(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    assets_path = _assets(tmp_path, [{"name": "optional.pdf", "size": 5}])

    summary = check_release_asset_listing.check_release_asset_listing(
        manifest_path,
        assets_path,
        require_exact=True,
    )

    assert summary["ok"] is False
    assert summary["exit_code"] == 1
    assert summary["missing_required"] == [{"name": "required.zip", "expected_bytes": 10}]


def test_cli_json_outputs_machine_readable_summary(tmp_path: Path, capsys) -> None:
    manifest_path = _manifest(tmp_path)
    assets_path = _assets(tmp_path, [{"name": "required.zip", "size": 10}])

    exit_code = check_release_asset_listing.main(
        ["--manifest", str(manifest_path), "--assets-json", str(assets_path), "--json"]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out)["missing_optional"] == [
        {"name": "optional.pdf", "expected_bytes": 5}
    ]
    assert captured.err == ""


def test_cli_require_exact_json_returns_nonzero_for_non_exact_listing(tmp_path: Path, capsys) -> None:
    manifest_path = _manifest(tmp_path)
    assets_path = _assets(
        tmp_path,
        [
            {"name": "required.zip", "size": 10},
            {"name": "extra.txt", "size": 1},
        ],
    )

    exit_code = check_release_asset_listing.main(
        [
            "--manifest",
            str(manifest_path),
            "--assets-json",
            str(assets_path),
            "--require-exact",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["ok"] is False
    assert payload["require_exact"] is True
    assert payload["totals"]["missing_optional"] == 1
    assert payload["totals"]["extra_assets"] == 1
    assert captured.err == ""


def test_cli_human_output_marks_warning_mode(tmp_path: Path, capsys) -> None:
    manifest_path = _manifest(tmp_path)
    assets_path = _assets(tmp_path, [{"name": "required.zip", "size": 10}])

    exit_code = check_release_asset_listing.main(
        ["--manifest", str(manifest_path), "--assets-json", str(assets_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Release asset listing preflight completed with warnings" in captured.out
    assert captured.err == ""
