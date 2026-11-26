from collections.abc import Mapping
from pathlib import Path
from threading import Barrier, Event

import pytest

from drift.collectors import engine
from drift.collectors.base import (
    CollectorContext,
    CollectorId,
    CollectorResult,
    CollectorSpec,
    CollectorStatus,
    Observation,
    ProbeIssue,
    ProbeResult,
)
from drift.collectors.engine import run_collectors
from drift.config import ProjectConfig


def test_runs_enabled_collectors_concurrently_in_stable_order(tmp_path: Path) -> None:
    barrier = Barrier(2, timeout=2)
    config = ProjectConfig.model_validate(
        {"schema_version": 1, "collectors": {"git": False}}
    )

    def collect(context: CollectorContext) -> Mapping[str, ProbeResult]:
        assert context.root == tmp_path
        assert 0 < context.remaining() <= 8
        barrier.wait()
        return {"second": Observation("ok"), "first": Observation(False)}

    spec = CollectorSpec(("second", "first"), collect)
    results = run_collectors(
        tmp_path, config, {"system": spec, "git": spec, "runtime": spec}
    )

    assert list(results) == ["git", "runtime", "system"]
    assert results["git"] == CollectorResult("disabled", {})
    assert results["system"].status == results["runtime"].status == "ok"
    assert list(results["system"].probes) == ["first", "second"]


@pytest.mark.parametrize("wrong_keys", [False, True])
def test_isolates_collector_failures(tmp_path: Path, wrong_keys: bool) -> None:
    def broken(_context: CollectorContext) -> Mapping[str, ProbeResult]:
        if wrong_keys:
            return {"secret-sentinel": Observation("secret-value")}
        raise RuntimeError("secret-sentinel")

    results = run_collectors(
        tmp_path,
        ProjectConfig.model_validate({"schema_version": 1}),
        {
            "runtime": CollectorSpec(("python",), broken),
            "system": CollectorSpec(("os",), lambda _: {"os": Observation("test")}),
        },
    )

    assert results["runtime"] == CollectorResult(
        "failed", {"python": ProbeIssue("failed", "collector_error")}
    )
    assert results["system"].status == "ok"
    assert "secret" not in repr(results)


def test_overdue_collector_does_not_hold_up_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = Event()
    release = Event()
    monkeypatch.setattr(engine, "_COLLECTOR_TIMEOUT", 0.15)

    def stalled(_context: CollectorContext) -> Mapping[str, ProbeResult]:
        started.set()
        release.wait(timeout=3)
        return {"python": Observation("late")}

    try:
        results = run_collectors(
            tmp_path,
            ProjectConfig.model_validate({"schema_version": 1}),
            {
                "runtime": CollectorSpec(("python",), stalled),
                "system": CollectorSpec(
                    ("os",), lambda _: {"os": Observation("ready")}
                ),
            },
        )
        assert started.is_set()
        assert results["runtime"] == CollectorResult(
            "failed", {"python": ProbeIssue("failed", "timeout")}
        )
        assert results["system"].status == "ok"
    finally:
        release.set()


@pytest.mark.parametrize(
    ("collector_id", "probes", "status"),
    [
        (
            "dependency",
            {"manifest:go.mod": ProbeIssue("unavailable", "not_found")},
            "ok",
        ),
        (
            "environment",
            {"file:.env": ProbeIssue("unavailable", "not_found")},
            "unavailable",
        ),
        (
            "runtime",
            {"python": ProbeIssue("unavailable", "executable_missing")},
            "unavailable",
        ),
        (
            "runtime",
            {"python": ProbeIssue("unsupported", "unsupported_launcher")},
            "unsupported",
        ),
        (
            "runtime",
            {
                "python": ProbeIssue("unavailable", "executable_missing"),
                "node": ProbeIssue("failed", "timeout"),
            },
            "partial",
        ),
        (
            "docker",
            {
                "installed": Observation(False),
                "client_version": ProbeIssue("not_applicable", "prerequisite_missing"),
            },
            "unavailable",
        ),
    ],
)
def test_rollup(
    tmp_path: Path,
    collector_id: CollectorId,
    probes: dict[str, ProbeResult],
    status: CollectorStatus,
) -> None:
    result = run_collectors(
        tmp_path,
        ProjectConfig.model_validate({"schema_version": 1}),
        {collector_id: CollectorSpec(tuple(probes), lambda _: probes)},
    )[collector_id]

    assert result == CollectorResult(status, probes)
