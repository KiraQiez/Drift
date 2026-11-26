# Drift coding agent rules

## Gather context

1. Read the [product requirements](../../docs/PRD.md) for the MVP boundary and the [development guide](../../docs/DEVELOPMENT.md) for shared engineering and testing standards.
2. Inspect the workspace and read the [roadmap](../../docs/ROADMAP.md#implementation-checklist). For implementation work, identify the approved task and review its dependencies, requirement IDs, and acceptance criteria.
3. Read the [architecture](../../docs/ARCHITECTURE.md), [security design](../../docs/SECURITY.md), and the relevant [CLI](../../docs/CLI_SPEC.md), [data](../../docs/DATA_MODEL.md), or [release](../../docs/RELEASE.md) contract.

## Work within the approved scope

- Outline a focused implementation plan before changing application code. Preserve unrelated work and keep changes within the requested task.
- Keep the shared docs authoritative for behavior and design. When a requirement conflicts with another requirement, surface the conflict before implementing the affected behavior.
- Add or update the applicable tests with behavior changes. Follow the [shared quality gates](../../docs/DEVELOPMENT.md#quality-gates-and-ci).

## Finish and report

- Run the applicable checks and review the result against the task's acceptance criteria and the security contract.
- Update the documents that own changed behavior and record consequential architecture decisions in [ARCHITECTURE.md](../../docs/ARCHITECTURE.md#design-decisions).
- Mark an implementation task complete only after verifying its acceptance criteria. Record the evidence in the roadmap and report completed work, checks actually run, limitations, and the next eligible task.
