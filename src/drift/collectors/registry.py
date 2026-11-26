"""Build the registry of collectors supported for a project."""

from drift.collectors import runtime, system
from drift.collectors.base import CollectorId, CollectorSpec
from drift.config import ProjectConfig


def build_registry(config: ProjectConfig) -> dict[CollectorId, CollectorSpec]:
    return {
        "system": CollectorSpec(system.PROBE_IDS, system.collect),
        "runtime": CollectorSpec(runtime.PROBE_IDS, runtime.collect),
    }
