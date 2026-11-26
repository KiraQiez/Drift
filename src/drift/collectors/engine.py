"""Schedule registered collectors and isolate failures."""

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path
from time import monotonic

from drift.collectors.base import (
    COLLECTOR_IDS,
    CollectorContext,
    CollectorId,
    CollectorResult,
    CollectorSpec,
    CollectorStatus,
    DiagnosticCode,
    Observation,
    ProbeIssue,
    ProbeResult,
    known_absence,
)
from drift.config import ProjectConfig

_COLLECTOR_TIMEOUT = 8.0
_PRIMARY_PROBE: dict[CollectorId, str] = {"docker": "installed", "git": "repository"}


def collector_status(
    collector_id: CollectorId, probes: Mapping[str, ProbeResult]
) -> CollectorStatus:
    applicable = [
        probe for probe in probes.values() if probe.status != "not_applicable"
    ]
    gaps = [
        probe
        for probe in applicable
        if isinstance(probe, ProbeIssue)
        and not (
            probe.status == "unavailable" and known_absence(collector_id, probe.code)
        )
    ]
    if gaps:
        if len(gaps) != len(applicable):
            return "partial"
        if any(probe.status == "failed" for probe in gaps):
            return "failed"
        if any(probe.status == "unsupported" for probe in gaps):
            return "unsupported"
        return "unavailable"

    primary = probes.get(_PRIMARY_PROBE.get(collector_id, ""))
    if isinstance(primary, Observation) and primary.value is False:
        return "unavailable"
    if (
        collector_id == "runtime"
        and applicable
        and all(probe.status == "unavailable" for probe in applicable)
    ):
        return "unavailable"
    return "ok"


def _failed(collector: CollectorSpec, code: DiagnosticCode) -> CollectorResult:
    return CollectorResult(
        "failed", dict.fromkeys(sorted(collector.probe_ids), ProbeIssue("failed", code))
    )


def _collect(
    collector_id: CollectorId, collector: CollectorSpec, context: CollectorContext
) -> CollectorResult:
    if not context.remaining():
        return _failed(collector, "timeout")
    try:
        observations = collector.collect(context)
        if observations.keys() != set(collector.probe_ids):
            return _failed(collector, "collector_error")
        probes = dict(sorted(observations.items()))
        return CollectorResult(collector_status(collector_id, probes), probes)
    except Exception:
        return _failed(collector, "collector_error")


def run_collectors(
    root: Path, config: ProjectConfig, registry: Mapping[CollectorId, CollectorSpec]
) -> dict[CollectorId, CollectorResult]:
    """Run enabled entries from a caller-supplied internal registry in stable order."""
    registry = {key: registry[key] for key in COLLECTOR_IDS if key in registry}
    enabled = config.collectors.model_dump()
    active = [key for key in registry if enabled[key]]
    results = {key: CollectorResult("disabled", {}) for key in registry}
    if not active:
        return results

    deadline = monotonic() + _COLLECTOR_TIMEOUT
    pool = ThreadPoolExecutor(max_workers=len(active))
    try:
        futures = {
            pool.submit(
                _collect,
                key,
                registry[key],
                CollectorContext(root, config.model_copy(deep=True), deadline),
            ): key
            for key in active
        }
        finished, overdue = wait(futures, timeout=max(0.0, deadline - monotonic()))
        for future in finished:
            results[futures[future]] = future.result()
        for future in overdue:
            key = futures[future]
            results[key] = _failed(registry[key], "timeout")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return results
