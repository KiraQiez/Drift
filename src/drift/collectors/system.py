"""Collect product and architecture information from the current system."""

import platform

from drift.collectors.base import CollectorContext, Observation, ProbeIssue, ProbeResult

PROBE_IDS = ("os", "os_version", "architecture")


def collect(_context: CollectorContext) -> dict[str, ProbeResult]:
    name = platform.system()
    version = platform.mac_ver()[0] if name == "Darwin" else ""
    return {
        key: Observation(value) if value else ProbeIssue("failed", "invalid_output")
        for key, value in zip(
            PROBE_IDS,
            (name, version or platform.release(), platform.machine()),
            strict=True,
        )
    }
