import os
import shutil
import subprocess
from time import monotonic

import pytest

from drift.collectors import git
from drift.collectors.base import CollectorContext, Observation, ProbeIssue
from drift.config import ProjectConfig


def collect(root):
    return git.collect(
        CollectorContext(root, ProjectConfig(schema_version=1), monotonic() + 8)
    )


@pytest.fixture
def checkout(tmp_path):
    executable = shutil.which("git")
    if executable is None:
        pytest.skip("Git is unavailable")
    env = {
        key: os.environ[key]
        for key in ("PATH", "SYSTEMROOT", "WINDIR")
        if key in os.environ
    }
    env.update(
        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_ALLOW_PROTOCOL=""
    )

    def command(*args):
        completed = subprocess.run(
            [
                executable,
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "-c",
                f"core.hooksPath={os.devnull}",
                *args,
            ],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            env=env,
            timeout=8,
        )
        return completed.stdout.strip()

    command("init", "--initial-branch=fixture", "--template=")
    return tmp_path, command


def test_git_worktree_states(checkout, monkeypatch):
    root, command = checkout
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "must-not-run")
    assert collect(root) == {
        "repository": Observation(True),
        "branch": Observation("fixture"),
        "commit": ProbeIssue("not_applicable", "unborn_head"),
        "worktree": Observation("clean"),
    }
    command("commit", "--allow-empty", "-m", "fixture")
    oid = command("rev-parse", "HEAD").decode("ascii")
    assert collect(root)["commit"] == Observation(oid)
    assert collect(root)["worktree"] == Observation("clean")
    (root / "secret-untracked-filename").touch()
    result = collect(root)
    assert result["worktree"] == Observation("dirty")
    assert "secret-untracked-filename" not in repr(result)
    command("checkout", "--detach")
    assert collect(root)["branch"] == ProbeIssue("not_applicable", "detached_head")


@pytest.mark.parametrize(
    "key",
    [
        "include.path",
        "includeIf.gitdir:/.path",
        "core.fsmonitor",
        "core.hooksPath",
        "filter.fixture.clean",
        "remote.fixture.promisor",
        "core.worktree",
    ],
)
def test_unsafe_configuration_stops_before_status(checkout, monkeypatch, key):
    root, command = checkout
    command("config", "--local", key, "sentinel-must-not-run")
    run = git.run_probe

    def check_command(executable, args, **kwargs):
        assert "status" not in args
        assert "--no-includes" in args
        return run(executable, args, **kwargs)

    monkeypatch.setattr(git, "run_probe", check_command)
    result = collect(root)
    assert result["worktree"] == ProbeIssue("unsupported", "unsupported_checkout")
    assert "sentinel" not in repr(result)


def test_git_absent_and_external_metadata_rejected(tmp_path, checkout, monkeypatch):
    root, _ = checkout
    child = tmp_path / "child"
    child.mkdir()
    monkeypatch.setattr(
        git, "run_probe", lambda *args, **kwargs: pytest.fail("must not start Git")
    )
    assert collect(child)["repository"] == Observation(False)
    (child / ".git").write_text("gitdir: ../.git", encoding="utf-8")
    assert collect(child)["repository"] == ProbeIssue(
        "unsupported", "unsupported_checkout"
    )
    alternates = root / ".git/objects/info/alternates"
    alternates.parent.mkdir(exist_ok=True)
    alternates.write_text("sentinel-external", encoding="utf-8")
    assert collect(root)["worktree"] == ProbeIssue(
        "unsupported", "unsupported_checkout"
    )


def test_git_rejects_linked_metadata(checkout, monkeypatch):
    root, _ = checkout
    linked = root / ".git/refs/heads/linked"
    try:
        linked.symlink_to(root / ".git/config")
    except OSError:
        pytest.skip("Symlinks are unavailable")
    monkeypatch.setattr(
        git, "run_probe", lambda *args, **kwargs: pytest.fail("must not start Git")
    )
    assert collect(root)["worktree"] == ProbeIssue(
        "unsupported", "unsupported_checkout"
    )
