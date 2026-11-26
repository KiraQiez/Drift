from pathlib import Path
from time import monotonic

import pytest

from drift.collectors import docker
from drift.collectors.base import CollectorContext, Observation, ProbeIssue
from drift.collectors.runner import CommandOutput
from drift.config import ProjectConfig


def context(root, project=None):
    config = ProjectConfig.model_validate(
        {"schema_version": 1, "docker": {"compose_project": project}}
    )
    return CollectorContext(root, config, monotonic() + 8)


def test_missing_docker_stops_before_daemon_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr(
        docker,
        "run_probe",
        lambda *args, **kwargs: ProbeIssue("unavailable", "executable_missing"),
    )
    monkeypatch.setattr(docker, "_endpoint", lambda: pytest.fail("no Docker client"))
    result = docker.collect(context(tmp_path))
    assert result["installed"] == Observation(False)
    assert result["daemon_reachable"] == ProbeIssue(
        "not_applicable", "prerequisite_missing"
    )
    assert result["services"] == ProbeIssue("not_applicable", "not_configured")


def test_docker_requests_only_configured_services(tmp_path, monkeypatch):
    host = "unix:///var/run/docker.sock"
    monkeypatch.setattr(docker, "_endpoint", lambda: host)
    monkeypatch.setattr(docker, "_socket_issue", lambda *args: None)
    monkeypatch.setenv("DOCKER_HOST", "tcp://remote.invalid:1234")
    commands = []

    def run(executable, args, *, cwd, deadline, docker_config, classify_exit):
        assert executable == "docker"
        assert docker_config.parent == tmp_path
        assert not docker_config.exists()
        assert args[:2] == ("--config", str(docker_config))
        command = args[2:]
        commands.append(command)
        if command == ("--version",):
            return CommandOutput(b"Docker version 29.1.0, build abc123", b"")
        if command == ("compose", "version"):
            return CommandOutput(b"Docker Compose version v2.42.0", b"")
        if command == ("--host", host, "version", "--format", "{{.Server.Version}}"):
            return CommandOutput(b"29.1.0", b"")
        assert command == (
            "--host",
            host,
            "container",
            "ls",
            "--all",
            "--filter",
            "label=com.docker.compose.project=demo",
            "--format",
            docker._FORMAT,
        )
        return CommandOutput(
            b'"db"\t"running"\n"api"\t"exited"\n"db"\t"running"\n', b""
        )

    monkeypatch.setattr(docker, "run_probe", run)
    result = docker.collect(context(tmp_path, "demo"))
    assert len(commands) == 4
    assert result == {
        "installed": Observation(True),
        "client_version": Observation("29.1.0"),
        "compose_installed": Observation(True),
        "compose_version": Observation("2.42.0"),
        "daemon_reachable": Observation(True),
        "services": Observation({"api": {"exited": 1}, "db": {"running": 2}}),
    }
    assert list(tmp_path.iterdir()) == []
    docker.collect(context(tmp_path))
    assert len(commands) == 7


@pytest.mark.parametrize(
    "error", [ConnectionRefusedError, FileNotFoundError, PermissionError, TimeoutError]
)
def test_docker_socket_failure_classification(tmp_path, monkeypatch, error):
    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def settimeout(self, timeout):
            assert 0 < timeout <= 2

        def connect(self, address):
            assert address == "/var/run/docker.sock"
            raise error("private raw error")

    monkeypatch.setattr(docker.socket, "socket", lambda *_: Socket())
    monkeypatch.setattr(docker.socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(docker, "_endpoint", lambda: "unix:///var/run/docker.sock")
    monkeypatch.setattr(
        docker,
        "_user_compose",
        lambda *args: ProbeIssue("unavailable", "executable_missing"),
    )

    def run(_tool, args, *, classify_exit, **kwargs):
        if args[2:] == ("--version",):
            return CommandOutput(b"Docker version 29.1.0", b"")
        if args[2:] == ("compose", "version"):
            return classify_exit(b"docker: unknown command: docker compose")
        pytest.fail("Daemon must be checked before issuing commands")

    monkeypatch.setattr(docker, "run_probe", run)
    result = docker.collect(context(tmp_path, "demo"))
    assert result["compose_installed"] == Observation(False)
    if error in (ConnectionRefusedError, FileNotFoundError):
        assert result["daemon_reachable"] == Observation(False)
        assert result["services"] == ProbeIssue("unavailable", "daemon_unreachable")
    else:
        code = "permission_denied" if error is PermissionError else "timeout"
        assert (
            result["daemon_reachable"]
            == result["services"]
            == ProbeIssue("failed", code)
        )


def test_user_compose_uses_only_standard_location(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(docker.sys, "platform", "darwin")
    plugin = home / ".docker/cli-plugins/docker-compose"
    plugin.parent.mkdir(parents=True)
    plugin.touch()
    socket = home / ".docker/run/docker.sock"
    socket.parent.mkdir()
    socket.touch()
    assert docker._endpoint() == f"unix://{socket}"

    def run(executable, args, **kwargs):
        assert executable == plugin.resolve()
        assert args == ("version", "--short")
        return CommandOutput(b"v2.42.0", b"")

    monkeypatch.setattr(docker, "run_probe", run)
    assert docker._user_compose(context(root), root / "isolated") == CommandOutput(
        b"v2.42.0", b""
    )
    assert docker._user_compose(context(home), root / "isolated") == ProbeIssue(
        "unsupported", "unsupported_launcher"
    )


def test_malformed_services_and_windows_daemon_messages():
    assert docker._services(CommandOutput(b'"api"\t"secret-state"', b"")) == ProbeIssue(
        "failed", "invalid_output"
    )
    assert docker._services(CommandOutput(b"", b"")) == Observation({})
    assert docker._daemon_exit(
        b"open //./pipe/docker_engine: The system cannot find the file specified."
    ) == ProbeIssue(
        "unavailable",
        "daemon_unreachable",
    )
    assert docker._daemon_exit(
        b"open //./pipe/docker_engine: Access is denied."
    ) == ProbeIssue("failed", "permission_denied")
    assert docker._daemon_exit(b"unexpected secret message") == ProbeIssue(
        "failed", "command_failed"
    )
