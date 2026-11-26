import os
import subprocess
import sys
from pathlib import Path
from time import monotonic

import pytest

from drift.collectors import runner
from drift.collectors.base import ProbeIssue
from drift.collectors.runner import CommandOutput, run_probe


@pytest.fixture
def executable(monkeypatch: pytest.MonkeyPatch) -> str:
    interpreter = Path(sys.executable)
    monkeypatch.setenv("PATH", str(interpreter.parent))
    return interpreter.name


def test_output_is_transient_and_environment_is_filtered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, executable: str
) -> None:
    monkeypatch.setenv("DRIFT_TEST_SECRET", "secret-sentinel")
    monkeypatch.setenv("PYTHONPATH", "startup-sentinel")
    monkeypatch.setenv("PATH", os.environ["PATH"] + os.pathsep + "relative-bin")
    output = run_probe(
        executable,
        (
            "-c",
            "import os, sys; "
            "assert 'DRIFT_TEST_SECRET' not in os.environ; "
            "assert 'PYTHONPATH' not in os.environ; "
            "assert 'relative-bin' not in os.environ['PATH']; "
            "assert sys.stdin.read() == ''; "
            "print(sys.argv[1], end=''); sys.stderr.write('other-stream')",
            "literal & argument",
        ),
        cwd=tmp_path,
        deadline=monotonic() + 3,
    )

    assert output == CommandOutput(b"literal & argument", b"other-stream")
    assert "other-stream" not in repr(output)


@pytest.mark.parametrize(
    ("extra", "expected"),
    [(0, None), (1, ProbeIssue("failed", "output_limit"))],
)
def test_combined_output_limit(
    tmp_path: Path, executable: str, extra: int, expected: ProbeIssue | None
) -> None:
    half = 128 * 1024
    output = run_probe(
        executable,
        (
            "-c",
            f"import sys; sys.stdout.write('a' * {half}); sys.stderr.write('b' * {half + extra})",
        ),
        cwd=tmp_path,
        deadline=monotonic() + 3,
    )
    assert output == (expected or CommandOutput(b"a" * half, b"b" * half))


def test_failed_command_discards_both_streams(tmp_path: Path, executable: str) -> None:
    output = run_probe(
        executable,
        ("-c", "import sys; print('secret'); sys.exit('another-secret')"),
        cwd=tmp_path,
        deadline=monotonic() + 3,
    )
    assert output == ProbeIssue("failed", "command_failed")


@pytest.mark.parametrize(("process_budget", "collector_budget"), [(0.2, 4), (2, 0.2)])
def test_shorter_deadline_kills_and_reaps_the_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    executable: str,
    process_budget: float,
    collector_budget: float,
) -> None:
    start = subprocess.Popen
    children: list[subprocess.Popen[bytes]] = []

    def record_child(*args, **kwargs):
        child = start(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(runner, "_COMMAND_TIMEOUT", process_budget)
    monkeypatch.setattr(runner.subprocess, "Popen", record_child)
    before = monotonic()
    output = run_probe(
        executable,
        ("-c", "import time; time.sleep(10)"),
        cwd=tmp_path,
        deadline=before + collector_budget,
    )

    assert output == ProbeIssue("failed", "timeout")
    assert monotonic() - before < 1.5
    assert len(children) == 1 and children[0].returncode is not None


def test_ignores_current_directory_and_relative_path_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "bin"
    folder.mkdir()
    suffix = ".exe" if os.name == "nt" else ""
    for directory in (tmp_path, folder):
        launcher = directory / f"fixture-tool{suffix}"
        launcher.touch(mode=0o755)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", os.pathsep.join(("", "bin")))

    output = run_probe("fixture-tool", (), cwd=tmp_path, deadline=monotonic() + 2)

    assert output == ProbeIssue("unavailable", "executable_missing")


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_inherited_pipes_do_not_extend_deadline(
    tmp_path: Path, executable: str
) -> None:
    before = monotonic()
    output = run_probe(
        executable,
        (
            "-c",
            "import subprocess, sys; "
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3)'])",
        ),
        cwd=tmp_path,
        deadline=before + 0.25,
    )

    assert output == ProbeIssue("failed", "timeout")
    assert monotonic() - before < 1.5


def test_expired_deadline_and_path_like_launcher(tmp_path: Path) -> None:
    assert run_probe(
        "fixture-tool", (), cwd=tmp_path, deadline=monotonic()
    ) == ProbeIssue("failed", "timeout")
    assert run_probe(
        "./fixture-tool", (), cwd=tmp_path, deadline=monotonic() + 2
    ) == ProbeIssue("failed", "invalid_input")


@pytest.mark.skipif(os.name != "nt", reason="Native Windows launcher policy")
def test_windows_batch_launcher_is_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "fixture-tool.cmd").write_text("@echo unexpected", encoding="utf-8")
    monkeypatch.setenv("PATH", str(tmp_path))

    output = run_probe("fixture-tool", (), cwd=tmp_path, deadline=monotonic() + 2)

    assert output == ProbeIssue("unsupported", "unsupported_launcher")
