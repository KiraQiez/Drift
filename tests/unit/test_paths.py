import os
from pathlib import Path

import pytest

from drift import paths
from drift.config import load_config
from drift.exceptions import UnsafePathError


@pytest.mark.parametrize(
    "relative_path",
    [
        "",
        ".",
        "..",
        "./.env",
        "parent/../.env",
        "/.env",
        "sub//.env",
        "sub/.env/",
        "C:/file",
        "C:file",
        r"sub\file",
        r"\\server\share",
        "NUL.txt",
        "dir/COM¹.env",
        "aux .env",
        "CONOUT$",
        ".env ",
        "dir./.env",
        "file:stream",
        "*.env",
        "bad\x00name",
    ],
)
def test_rejects_unsafe_path_syntax(tmp_path: Path, relative_path: str) -> None:
    with (
        pytest.raises(UnsafePathError),
        paths.open_project_file(tmp_path, relative_path),
    ):
        pytest.fail("Unsafe input was opened.")


@pytest.fixture(params=[False, True], ids=["fallback", "descriptor"])
def read_mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.param and not paths._DESCRIPTOR_READS:
        pytest.skip("Descriptor-relative reads are unavailable.")
    monkeypatch.setattr(paths, "_DESCRIPTOR_READS", request.param)


@pytest.mark.usefixtures("read_mode")
def test_reads_regular_file_and_reports_missing_file(tmp_path: Path) -> None:
    directory = tmp_path / "with spaces"
    directory.mkdir()
    (directory / ".env").write_bytes(b"fixture")

    with paths.open_project_file(tmp_path, "with spaces/.env") as stream:
        assert stream.read() == b"fixture"
    assert stream.closed
    with (
        pytest.raises(FileNotFoundError),
        paths.open_project_file(tmp_path, "with spaces/missing"),
    ):
        pytest.fail("A missing file was opened.")
    with (
        pytest.raises(UnsafePathError),
        paths.open_project_file(tmp_path, "with spaces"),
    ):
        pytest.fail("A directory was opened as a file.")


@pytest.mark.usefixtures("read_mode")
def test_rejects_symlinks_at_each_level(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "settings").write_text("schema_version = 1", encoding="utf-8")
    try:
        (root / "drift.toml").symlink_to(outside / "settings")
        (root / "linked").symlink_to(outside, target_is_directory=True)
        (root / "broken").symlink_to(outside / "missing")
    except OSError:
        pytest.skip("Symlinks cannot be created on this system.")

    with pytest.raises(UnsafePathError):
        load_config(root)
    for relative_path in ("linked/settings", "broken"):
        with (
            pytest.raises(UnsafePathError),
            paths.open_project_file(root, relative_path),
        ):
            pytest.fail("A symbolic link was followed.")


@pytest.mark.usefixtures("read_mode")
@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFOs are unavailable")
def test_rejects_fifo(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "pipe")
    with pytest.raises(UnsafePathError), paths.open_project_file(tmp_path, "pipe"):
        pytest.fail("A FIFO was opened.")


@pytest.mark.skipif(
    not paths._DESCRIPTOR_READS, reason="Requires no-follow descriptors"
)
def test_blocks_symlink_substitution_during_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    inside = root / "config"
    inside.touch()
    outside = tmp_path / "outside"
    outside.touch()
    open_file = os.open

    def replace_then_open(
        path: str | Path, flags: int, *, dir_fd: int | None = None
    ) -> int:
        if path == "config":
            inside.unlink()
            inside.symlink_to(outside)
        return open_file(path, flags, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", replace_then_open)
    with pytest.raises(UnsafePathError), paths.open_project_file(root, "config"):
        pytest.fail("A substituted symbolic link was followed.")
