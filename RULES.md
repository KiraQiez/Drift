# Contribution rules

These rules apply to human and AI contributors. The [development guide](docs/DEVELOPMENT.md) owns test practices and quality checks. AI contributors start with [AGENTS.md](AGENTS.md).

## Keep commits small

- Give each commit one logical purpose. Include the tests and docs that explain or verify that change. Split independent work into separate commits and leave unrelated edits out.
- Write an imperative subject that describes the change. Aim for 72 characters or fewer, for example `Validate project config paths`. Add a short body when the reason, compatibility impact, or tradeoff needs context.
- Review the staged diff before committing. Keep secrets, local build artifacts, and local Drift state out of Git.

## Keep code simple

- Follow DRY (Don't Repeat Yourself). Reuse existing behavior and keep shared rules in one place. Extract an abstraction when it removes real duplication or creates a useful test boundary. Keep code separate when its responsibilities differ.
- Implement the current requirement with the smallest design that meets it. Prefer composition and the Python standard library. Avoid speculative infrastructure, plugins, and dependencies. Keep development dependencies separate and record consequential dependency changes in the [architecture decisions](docs/ARCHITECTURE.md#design-decisions).
- Follow PEP 8 and the repository's Ruff settings. Use descriptive names, focused functions, and type annotations on public functions.
- Use `pathlib` for paths, timezone-aware UTC timestamps, and deterministic public output. Keep terminal formatting outside core logic. Use typed errors and handle unexpected failures at defined boundaries.

## Verify the change

- Follow the [security contract](docs/SECURITY.md), including bounded subprocesses, project-local writes, and value-free environment observations.
- Update the relevant tests and the document that owns any changed behavior. Run the [applicable checks](docs/DEVELOPMENT.md#quality-gates-and-ci) and report any verification gaps. Record implementation status and evidence in the [roadmap](docs/ROADMAP.md#implementation-checklist).
