from dataclasses import asdict

from drift.collectors.base import COLLECTOR_IDS, Observation, ProbeIssue
from drift.collectors.dependency import PROBE_IDS
from drift.collectors.engine import collector_status
from drift.comparison import Change, Gap, compare
from drift.models import CapturedEnvironment


def environment(probes=None, *, allowlist=None, compose=None, case="preserve"):
    probes = probes or {}
    return CapturedEnvironment.model_validate(
        {
            "scope": {
                "active_allowlist": allowlist,
                "active_name_case": case,
                "compose_project": compose,
            },
            "collectors": {
                name: {
                    "status": collector_status(name, probes[name])
                    if name in probes
                    else "disabled",
                    "probes": {
                        key: asdict(value)
                        for key, value in probes.get(name, {}).items()
                    },
                }
                for name in COLLECTOR_IDS
            },
        }
    )


def test_checksums_distinguish_added_removed_and_unknown():
    missing = ProbeIssue("unavailable", "not_found")
    before = dict.fromkeys(PROBE_IDS, missing)
    after = before.copy()
    before["manifest:go.mod"] = Observation("a" * 64)
    after["manifest:go.sum"] = Observation("b" * 64)
    before["manifest:uv.lock"] = after["manifest:uv.lock"] = ProbeIssue(
        "failed", "timeout"
    )
    result = compare(
        environment({"dependency": before}), environment({"dependency": after})
    )
    assert result.changes == [
        Change("dependency", "manifest:go.mod", None, "removed", "a" * 64, None),
        Change("dependency", "manifest:go.sum", None, "added", None, "b" * 64),
    ]
    assert result.gaps == [Gap("dependency", "manifest:uv.lock", "both", "timeout")]
    assert result.outcome == "drift" and result.exit_code == 3


def test_environment_scope_and_name_sets():
    before = environment(
        {
            "environment": {
                "active": Observation(["A"]),
                "file:old.env": Observation(["OLD"]),
                "file:common.env": Observation(["GONE", "SAME"]),
            }
        }
    )
    after = environment(
        {
            "environment": {
                "active": Observation(["B"]),
                "file:new.env": Observation(["NEW"]),
                "file:common.env": Observation(["ADDED", "SAME"]),
            }
        },
        allowlist=["B"],
    )
    result = compare(before, after)
    assert result.changes == [
        Change("environment", "file:common.env", "ADDED", "added", None, True),
        Change("environment", "file:common.env", "GONE", "removed", True, None),
    ]
    assert result.gaps == [
        Gap("environment", "active", "both", "scope_changed"),
        Gap("environment", "file:new.env", "reference", "scope_changed"),
        Gap("environment", "file:old.env", "current", "scope_changed"),
    ]


def test_docker_changes_and_prerequisite_gaps():
    absent = ProbeIssue("not_applicable", "prerequisite_missing")
    old = {
        "installed": Observation(False),
        "client_version": absent,
        "compose_installed": absent,
        "compose_version": absent,
        "daemon_reachable": absent,
        "services": absent,
    }
    current = {
        "installed": Observation(True),
        "client_version": Observation("28.0"),
        "compose_installed": Observation(True),
        "compose_version": Observation("5.5"),
        "daemon_reachable": Observation(True),
        "services": Observation({"db": {"running": 1}}),
    }
    result = compare(
        environment({"docker": old}, compose="proj"),
        environment({"docker": current}, compose="proj"),
    )
    assert result.changes == [
        Change("docker", "installed", None, "modified", False, True)
    ]
    assert result.gaps == [
        Gap("docker", "services", "reference", "prerequisite_missing")
    ]
    changed = current | {
        "services": Observation({"api": {"exited": 1}, "db": {"running": 2}})
    }
    assert compare(
        environment({"docker": current}, compose="proj"),
        environment({"docker": changed}, compose="proj"),
    ).changes == [
        Change("docker", "services", "api", "added", None, {"exited": 1}),
        Change("docker", "services", "db", "modified", {"running": 1}, {"running": 2}),
    ]


def test_disabled_git_and_no_comparable_observations():
    git = {
        "repository": Observation(True),
        "branch": Observation("different"),
        "commit": Observation("a" * 40),
        "worktree": Observation("dirty"),
    }
    reference = environment({"environment": {"active": Observation([])}})
    assert (
        compare(
            reference,
            environment({"environment": {"active": Observation([])}, "git": git}),
        ).exit_code
        == 0
    )
    result = compare(reference, environment({"git": git}))
    assert result.gaps == [Gap("environment", None, "current", "scope_changed")]
    assert result.warnings == ["no_comparable_observations"]
    assert result.exit_code == 4
