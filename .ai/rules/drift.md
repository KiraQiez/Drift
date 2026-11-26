# Drift coding agent rules

## Gather context

1. Read [AGENTS.md](../../AGENTS.md), the [contribution rules](../../RULES.md), and the relevant project documentation before making changes.
2. Inspect the workspace. Read the [implementation checklist](../../docs/ROADMAP.md#implementation-checklist) and identify the first pending task whose dependencies are complete, or verify the task the user explicitly selected. Review its requirement IDs and acceptance criteria.
3. Follow the [product requirements](../../docs/PRD.md), [architecture](../../docs/ARCHITECTURE.md), [security design](../../docs/SECURITY.md), [development guide](../../docs/DEVELOPMENT.md), and the relevant [CLI](../../docs/CLI_SPEC.md), [data](../../docs/DATA_MODEL.md), or [release](../../docs/RELEASE.md) contract.

## Brief the user before implementation

Use this five-point format before editing application code.

1. **Selected task** — Give its ID and name.
2. **Objective** — Describe the outcome.
3. **Files** — List what will be created or modified.
4. **Approach** — Explain how the change will work.
5. **Acceptance criteria** — Explain what will be verified.

Implement only the approved task and preserve unrelated work. If requirements conflict, surface the conflict before implementing the affected behavior. Keep the shared docs authoritative for behavior and design.

## Finish and report

- Add or update the necessary tests. Run the [applicable quality checks](../../docs/DEVELOPMENT.md#quality-gates-and-ci) and verify the acceptance criteria and security constraints.
- Update the documents that own changed behavior and record consequential architecture decisions in [ARCHITECTURE.md](../../docs/ARCHITECTURE.md#design-decisions).
- After successful verification, mark the task complete and record the evidence in the [implementation checklist](../../docs/ROADMAP.md#implementation-checklist). Report the completed work, checks actually run, any limitations, and the next eligible task.
- Obtain the user's approval before implementing a subsequent task.
