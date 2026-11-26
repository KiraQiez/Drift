"""Build the registry of collectors supported for a project."""

from drift.collectors import dependency, docker, environment, runtime, system
from drift.collectors.base import CollectorId, CollectorSpec
from drift.config import ProjectConfig


def build_registry(config: ProjectConfig) -> dict[CollectorId, CollectorSpec]:
    return {
        "dependency": CollectorSpec(dependency.PROBE_IDS, dependency.collect),
        "docker": CollectorSpec(docker.PROBE_IDS, docker.collect),
        "environment": CollectorSpec(
            environment.probe_ids(config), environment.collect
        ),
        "system": CollectorSpec(system.PROBE_IDS, system.collect),
        "runtime": CollectorSpec(runtime.PROBE_IDS, runtime.collect),
    }
