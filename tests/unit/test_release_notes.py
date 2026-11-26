import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "release_notes.py"

CHANGELOG = """# Changelog

## Unreleased

- Upcoming changes.

## 1.2.3

### Added

- Initial release.

## 1.2.2

- Previous release.
"""


def run_notes(tmp_path, ref, version, changelog=CHANGELOG):
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nversion = "{version}"\n', encoding="utf-8"
    )
    return subprocess.run(
        [sys.executable, str(SCRIPT), ref, "notes.md"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_extracts_only_matching_version_section(tmp_path):
    result = run_notes(tmp_path, "refs/tags/v1.2.3", "1.2.3")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "notes.md").read_text(encoding="utf-8") == (
        "### Added\n\n- Initial release.\n"
    )


def test_staging_uses_unreleased_notes(tmp_path):
    result = run_notes(tmp_path, "refs/heads/staging", "1.2.3.dev0")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "notes.md").read_text(
        encoding="utf-8"
    ) == "- Upcoming changes.\n"


@pytest.mark.parametrize(
    "ref",
    [
        "refs/heads/main",
        "refs/tags/1.2.3",
        "refs/tags/v1.2",
        "refs/tags/v01.2.3",
        "refs/tags/v1.2.3-rc.1",
        "refs/tags/v1.2.3+build",
    ],
)
def test_rejects_invalid_refs(tmp_path, ref):
    result = run_notes(tmp_path, ref, "1.2.3")
    assert result.returncode == 1 and "stable" in result.stderr
    assert not (tmp_path / "notes.md").exists()


def test_rejects_version_mismatch(tmp_path):
    result = run_notes(tmp_path, "refs/tags/v1.2.3", "1.2.3.dev0")
    assert result.returncode == 1 and "disagrees" in result.stderr


@pytest.mark.parametrize(
    "changelog",
    [
        "## Unreleased\n\n- Upcoming changes.\n",
        "## 1.2.3\n\n",
        "## 1.2.3\n\n- First.\n\n## 1.2.3\n\n- Second.\n",
    ],
)
def test_rejects_absent_empty_or_ambiguous_notes(tmp_path, changelog):
    result = run_notes(tmp_path, "refs/tags/v1.2.3", "1.2.3", changelog)
    assert result.returncode == 1 and "changelog" in result.stderr
